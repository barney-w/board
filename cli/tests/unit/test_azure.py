"""Tests for Azure modules — Key Vault state machine, resource groups, VM parsing.

All Azure SDK clients are mocked. No real Azure calls are made.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from board.azure.compute import list_vms
from board.azure.deployment import bicep_build, deploy, ensure_network, verify_resource_group
from board.azure.keyvault import (
    create_or_recover_vault,
    ensure_secrets_officer_role,
    get_secret,
    list_secrets,
    set_secret,
    set_secret_with_propagation_retry,
)
from board.core.errors import BoardError, DeploymentError

# ── Helpers ──


def _make_vault(name: str, uri: str) -> SimpleNamespace:
    """Create a mock vault object."""
    return SimpleNamespace(
        name=name,
        properties=SimpleNamespace(vault_uri=uri),
    )


def _make_poller(result_value: object) -> MagicMock:
    """Create a mock LRO poller that returns result_value."""
    poller = MagicMock()
    poller.result.return_value = result_value
    return poller


class _FakeHttpResponseError(Exception):
    """Stand-in for azure.core.exceptions.HttpResponseError in tests."""


class _FakeResourceNotFoundError(Exception):
    """Stand-in for azure.core.exceptions.ResourceNotFoundError in tests."""


# ── Key Vault State Machine Tests ──


class TestCreateOrRecoverVault:
    """Tests for the three-way state machine in create_or_recover_vault."""

    @pytest.mark.asyncio
    async def test_vault_already_exists(self) -> None:
        """If the vault exists, just return its URL."""
        vault = _make_vault("myvault", "https://myvault.vault.azure.net/")
        mock_client = MagicMock()
        mock_client.vaults.get.return_value = vault

        with patch("board.azure.keyvault.KeyVaultManagementClient", return_value=mock_client):
            url = await create_or_recover_vault(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                vault_name="myvault",
                location="australiaeast",
                tenant_id="tenant-abc",
            )

        assert url == "https://myvault.vault.azure.net/"
        mock_client.vaults.get.assert_called_once_with("rg-test", "myvault")

    @pytest.mark.asyncio
    async def test_soft_deleted_vault_recovered(self) -> None:
        """If vault is soft-deleted, it should be recovered."""
        from azure.core.exceptions import HttpResponseError

        vault = _make_vault("myvault", "https://myvault.vault.azure.net/")
        mock_client = MagicMock()
        # get() raises — vault doesn't exist in the RG
        mock_client.vaults.get.side_effect = HttpResponseError("Not found")
        # get_deleted() succeeds — soft-deleted vault found
        mock_client.vaults.get_deleted.return_value = SimpleNamespace(name="myvault")
        # recover returns a poller that yields the vault
        mock_client.vaults.begin_recover_deleted.return_value = _make_poller(vault)

        with patch("board.azure.keyvault.KeyVaultManagementClient", return_value=mock_client):
            url = await create_or_recover_vault(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                vault_name="myvault",
                location="australiaeast",
                tenant_id="tenant-abc",
            )

        assert url == "https://myvault.vault.azure.net/"
        mock_client.vaults.begin_recover_deleted.assert_called_once()

    @pytest.mark.asyncio
    async def test_fresh_creation(self) -> None:
        """If no vault exists (live or soft-deleted), create a new one."""
        from azure.core.exceptions import HttpResponseError

        vault = _make_vault("myvault", "https://myvault.vault.azure.net/")
        mock_client = MagicMock()
        mock_client.vaults.get.side_effect = HttpResponseError("Not found")
        mock_client.vaults.get_deleted.side_effect = HttpResponseError("Not found")
        mock_client.vaults.begin_create_or_update.return_value = _make_poller(vault)

        with patch("board.azure.keyvault.KeyVaultManagementClient", return_value=mock_client):
            url = await create_or_recover_vault(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                vault_name="myvault",
                location="australiaeast",
                tenant_id="tenant-abc",
            )

        assert url == "https://myvault.vault.azure.net/"
        mock_client.vaults.begin_create_or_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_conflict_then_purge_and_recreate(self) -> None:
        """If creation fails with conflict, purge soft-deleted and retry."""
        from azure.core.exceptions import HttpResponseError

        vault = _make_vault("myvault", "https://myvault.vault.azure.net/")
        mock_client = MagicMock()
        mock_client.vaults.get.side_effect = HttpResponseError("Not found")
        # First get_deleted fails (not yet visible), then succeeds on retry
        mock_client.vaults.get_deleted.side_effect = [
            HttpResponseError("Not found"),  # Initial check
            SimpleNamespace(name="myvault"),  # Found on retry
        ]
        # First create fails with conflict
        mock_client.vaults.begin_create_or_update.side_effect = [
            HttpResponseError("Conflict"),
            _make_poller(vault),  # Succeeds after purge
        ]
        mock_client.vaults.begin_purge_deleted.return_value = _make_poller(None)

        with (
            patch("board.azure.keyvault.KeyVaultManagementClient", return_value=mock_client),
            patch("board.azure.keyvault._KV_RETRY_DELAY", 0.01),
        ):
            url = await create_or_recover_vault(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                vault_name="myvault",
                location="australiaeast",
                tenant_id="tenant-abc",
            )

        assert url == "https://myvault.vault.azure.net/"
        mock_client.vaults.begin_purge_deleted.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self) -> None:
        """If all retries fail, raise BoardError."""
        from azure.core.exceptions import HttpResponseError

        mock_client = MagicMock()
        mock_client.vaults.get.side_effect = HttpResponseError("Not found")
        mock_client.vaults.get_deleted.side_effect = HttpResponseError("Not found")
        mock_client.vaults.begin_create_or_update.side_effect = HttpResponseError("Conflict")

        with (
            patch("board.azure.keyvault.KeyVaultManagementClient", return_value=mock_client),
            patch("board.azure.keyvault._KV_RETRY_DELAY", 0.01),
            pytest.raises(BoardError, match="Failed to create Key Vault"),
        ):
            await create_or_recover_vault(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                vault_name="myvault",
                location="australiaeast",
                tenant_id="tenant-abc",
            )


# ── Key Vault Secret Tests ──


class TestKeyVaultSecrets:
    @pytest.mark.asyncio
    async def test_get_secret_found(self) -> None:
        mock_secret = SimpleNamespace(value="supersecret")
        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        with patch("board.azure.keyvault.SecretClient", return_value=mock_client):
            result = await get_secret(
                "https://myvault.vault.azure.net/",
                MagicMock(),
                "my-secret",
            )

        assert result == "supersecret"

    @pytest.mark.asyncio
    async def test_get_secret_not_found(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        mock_client = MagicMock()
        mock_client.get_secret.side_effect = ResourceNotFoundError("Not found")

        with patch("board.azure.keyvault.SecretClient", return_value=mock_client):
            result = await get_secret(
                "https://myvault.vault.azure.net/",
                MagicMock(),
                "no-such-secret",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_set_secret(self) -> None:
        mock_client = MagicMock()

        with patch("board.azure.keyvault.SecretClient", return_value=mock_client):
            await set_secret(
                "https://myvault.vault.azure.net/",
                MagicMock(),
                "my-secret",
                "newvalue",
            )

        mock_client.set_secret.assert_called_once_with("my-secret", "newvalue")

    @pytest.mark.asyncio
    async def test_list_secrets(self) -> None:
        mock_client = MagicMock()
        mock_client.list_properties_of_secrets.return_value = [
            SimpleNamespace(name="secret-a"),
            SimpleNamespace(name="secret-b"),
            SimpleNamespace(name="secret-c"),
        ]

        with patch("board.azure.keyvault.SecretClient", return_value=mock_client):
            names = await list_secrets(
                "https://myvault.vault.azure.net/",
                MagicMock(),
            )

        assert names == ["secret-a", "secret-b", "secret-c"]


class TestSetSecretWithPropagationRetry:
    """RBAC for a freshly granted role can take 30s-2min to propagate;
    set_secret_with_propagation_retry retries on Forbidden then fails loud."""

    @pytest.mark.asyncio
    async def test_succeeds_first_try(self) -> None:
        mock_client = MagicMock()

        with patch("board.azure.keyvault.SecretClient", return_value=mock_client):
            await set_secret_with_propagation_retry(
                "https://kv.vault.azure.net/",
                MagicMock(),
                "k",
                "v",
                max_retries=3,
                delay_seconds=0,
            )

        mock_client.set_secret.assert_called_once_with("k", "v")

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self) -> None:
        from azure.core.exceptions import HttpResponseError

        forbidden = HttpResponseError(message="ForbiddenByRbac")
        forbidden.status_code = 403  # type: ignore[attr-defined]

        mock_client = MagicMock()
        mock_client.set_secret.side_effect = [forbidden, forbidden, None]

        with patch("board.azure.keyvault.SecretClient", return_value=mock_client):
            await set_secret_with_propagation_retry(
                "https://kv.vault.azure.net/",
                MagicMock(),
                "k",
                "v",
                max_retries=5,
                delay_seconds=0,
            )

        assert mock_client.set_secret.call_count == 3

    @pytest.mark.asyncio
    async def test_fails_after_max_retries(self) -> None:
        from azure.core.exceptions import HttpResponseError

        forbidden = HttpResponseError(message="ForbiddenByRbac")
        forbidden.status_code = 403  # type: ignore[attr-defined]

        mock_client = MagicMock()
        mock_client.set_secret.side_effect = forbidden

        with (
            patch("board.azure.keyvault.SecretClient", return_value=mock_client),
            pytest.raises(BoardError, match="after .* of retries"),
        ):
            await set_secret_with_propagation_retry(
                "https://kv.vault.azure.net/",
                MagicMock(),
                "k",
                "v",
                max_retries=2,
                delay_seconds=0,
            )

        assert mock_client.set_secret.call_count == 2

    @pytest.mark.asyncio
    async def test_non_forbidden_error_fails_immediately(self) -> None:
        """Non-403 errors are not transient — fail fast without retrying."""
        from azure.core.exceptions import HttpResponseError

        bad_request = HttpResponseError(message="BadParameter")
        bad_request.status_code = 400  # type: ignore[attr-defined]

        mock_client = MagicMock()
        mock_client.set_secret.side_effect = bad_request

        with (
            patch("board.azure.keyvault.SecretClient", return_value=mock_client),
            pytest.raises(BoardError, match="Failed to set secret"),
        ):
            await set_secret_with_propagation_retry(
                "https://kv.vault.azure.net/",
                MagicMock(),
                "k",
                "v",
                max_retries=5,
                delay_seconds=0,
            )

        assert mock_client.set_secret.call_count == 1


class TestEnsureSecretsOfficerRole:
    @pytest.mark.asyncio
    async def test_skips_if_already_assigned(self) -> None:
        existing = SimpleNamespace(
            role_definition_id=(
                "/subscriptions/sub/providers/Microsoft.Authorization"
                "/roleDefinitions/b86a8fe4-44ce-4948-aee5-eccb2c155cd7"
            ),
        )
        mock_client = MagicMock()
        mock_client.role_assignments.list_for_scope.return_value = [existing]

        with patch(
            "board.azure.keyvault.AuthorizationManagementClient",
            return_value=mock_client,
        ):
            await ensure_secrets_officer_role(MagicMock(), "sub", "/vault/id", "principal-1")

        mock_client.role_assignments.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_assignment_when_missing(self) -> None:
        mock_client = MagicMock()
        mock_client.role_assignments.list_for_scope.return_value = []

        with patch(
            "board.azure.keyvault.AuthorizationManagementClient",
            return_value=mock_client,
        ):
            await ensure_secrets_officer_role(MagicMock(), "sub", "/vault/id", "principal-1")

        mock_client.role_assignments.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_boarderror_on_create_failure(self) -> None:
        """Caller lacking roleAssignments/write should fail loud, not warn."""
        from azure.core.exceptions import HttpResponseError

        denied = HttpResponseError(message="AuthorizationFailed")
        mock_client = MagicMock()
        mock_client.role_assignments.list_for_scope.return_value = []
        mock_client.role_assignments.create.side_effect = denied

        with (
            patch(
                "board.azure.keyvault.AuthorizationManagementClient",
                return_value=mock_client,
            ),
            pytest.raises(BoardError, match="Could not assign 'Key Vault Secrets Officer'"),
        ):
            await ensure_secrets_officer_role(MagicMock(), "sub", "/vault/id", "principal-1")


# ── Resource Group Verification Tests ──


def _rg_object(state: str = "Succeeded", location: str = "australiaeast") -> SimpleNamespace:
    return SimpleNamespace(
        properties=SimpleNamespace(provisioning_state=state),
        location=location,
        tags={"environment": "dev"},
    )


def _role_assignment(role_id: str) -> SimpleNamespace:
    """Return a mock RoleAssignment with a fully-qualified role definition id."""
    return SimpleNamespace(
        role_definition_id=(
            f"/subscriptions/sub-123/providers/Microsoft.Authorization/roleDefinitions/{role_id}"
        ),
    )


CONTRIBUTOR = "b24988ac-6180-42a0-ab88-20f7382dd24c"
OWNER = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"
READER = "acdd72a7-3385-48ef-bd42-f606fba81ae7"


class TestVerifyResourceGroup:
    @pytest.mark.asyncio
    async def test_succeeds_with_contributor(self) -> None:
        """Caller has Contributor on a Succeeded RG -- returns location + tags."""
        rm = MagicMock()
        rm.resource_groups.check_existence.return_value = True
        rm.resource_groups.get.return_value = _rg_object()

        am = MagicMock()
        am.role_assignments.list_for_scope.return_value = iter([_role_assignment(CONTRIBUTOR)])

        with (
            patch("board.azure.deployment.ResourceManagementClient", return_value=rm),
            patch("board.azure.deployment.AuthorizationManagementClient", return_value=am),
        ):
            location, tags = await verify_resource_group(
                credential=MagicMock(),
                subscription_id="sub-123",
                name="rg-test",
                principal_id="oid-123",
            )

        assert location == "australiaeast"
        assert tags == {"environment": "dev"}

    @pytest.mark.asyncio
    async def test_succeeds_with_owner(self) -> None:
        """Owner is also accepted."""
        rm = MagicMock()
        rm.resource_groups.check_existence.return_value = True
        rm.resource_groups.get.return_value = _rg_object()

        am = MagicMock()
        am.role_assignments.list_for_scope.return_value = iter([_role_assignment(OWNER)])

        with (
            patch("board.azure.deployment.ResourceManagementClient", return_value=rm),
            patch("board.azure.deployment.AuthorizationManagementClient", return_value=am),
        ):
            await verify_resource_group(
                credential=MagicMock(),
                subscription_id="sub-123",
                name="rg-test",
                principal_id="oid-123",
            )

    @pytest.mark.asyncio
    async def test_rg_missing_raises(self) -> None:
        rm = MagicMock()
        rm.resource_groups.check_existence.return_value = False

        with (
            patch("board.azure.deployment.ResourceManagementClient", return_value=rm),
            pytest.raises(BoardError, match="not found"),
        ):
            await verify_resource_group(
                credential=MagicMock(),
                subscription_id="sub-123",
                name="rg-missing",
                principal_id="oid-123",
            )

    @pytest.mark.asyncio
    async def test_rg_deleting_raises(self) -> None:
        rm = MagicMock()
        rm.resource_groups.check_existence.return_value = True
        rm.resource_groups.get.return_value = _rg_object(state="Deleting")

        with (
            patch("board.azure.deployment.ResourceManagementClient", return_value=rm),
            pytest.raises(BoardError, match="being deleted"),
        ):
            await verify_resource_group(
                credential=MagicMock(),
                subscription_id="sub-123",
                name="rg-test",
                principal_id="oid-123",
            )

    @pytest.mark.asyncio
    async def test_reader_only_raises(self) -> None:
        """Reader is insufficient -- caller needs Contributor or Owner."""
        rm = MagicMock()
        rm.resource_groups.check_existence.return_value = True
        rm.resource_groups.get.return_value = _rg_object()

        am = MagicMock()
        am.role_assignments.list_for_scope.return_value = iter([_role_assignment(READER)])

        with (
            patch("board.azure.deployment.ResourceManagementClient", return_value=rm),
            patch("board.azure.deployment.AuthorizationManagementClient", return_value=am),
            pytest.raises(BoardError, match="Contributor or Owner"),
        ):
            await verify_resource_group(
                credential=MagicMock(),
                subscription_id="sub-123",
                name="rg-test",
                principal_id="oid-123",
            )

    @pytest.mark.asyncio
    async def test_no_assignments_raises(self) -> None:
        rm = MagicMock()
        rm.resource_groups.check_existence.return_value = True
        rm.resource_groups.get.return_value = _rg_object()

        am = MagicMock()
        am.role_assignments.list_for_scope.return_value = iter([])

        with (
            patch("board.azure.deployment.ResourceManagementClient", return_value=rm),
            patch("board.azure.deployment.AuthorizationManagementClient", return_value=am),
            pytest.raises(BoardError, match="Contributor or Owner"),
        ):
            await verify_resource_group(
                credential=MagicMock(),
                subscription_id="sub-123",
                name="rg-test",
                principal_id="oid-123",
            )

    @pytest.mark.asyncio
    async def test_missing_principal_id_raises(self) -> None:
        rm = MagicMock()
        rm.resource_groups.check_existence.return_value = True
        rm.resource_groups.get.return_value = _rg_object()

        with (
            patch("board.azure.deployment.ResourceManagementClient", return_value=rm),
            pytest.raises(BoardError, match="signed-in user"),
        ):
            await verify_resource_group(
                credential=MagicMock(),
                subscription_id="sub-123",
                name="rg-test",
                principal_id="",
            )


# ── ensure_network Tests ──


def _vnet_object(
    vnet_id: str = "/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-test",
    state: str = "Succeeded",
) -> SimpleNamespace:
    """Mock vnet object with id + provisioning_state, matching SDK shape."""
    return SimpleNamespace(id=vnet_id, provisioning_state=state)


def _subnet_object(
    subnet_id: str = (
        "/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.Network"
        "/virtualNetworks/vnet-test/subnets/snet-test"
    ),
    state: str = "Succeeded",
    nsg_id: str | None = (
        "/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.Network"
        "/networkSecurityGroups/nsg-test"
    ),
) -> SimpleNamespace:
    """Mock subnet object with id + provisioning_state + optional NSG, matching SDK shape."""
    nsg = SimpleNamespace(id=nsg_id) if nsg_id else None
    return SimpleNamespace(id=subnet_id, provisioning_state=state, network_security_group=nsg)


class TestEnsureNetwork:
    """Tests for ensure_network: idempotent shared-network discovery + deploy."""

    @pytest.mark.asyncio
    async def test_existing_vnet_and_subnet_returns_ids_no_deploy(self) -> None:
        """When both vnet+subnet exist and Succeeded, return IDs without deploying."""
        vnet_id = (
            "/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.Network"
            "/virtualNetworks/vnet-test"
        )
        subnet_id = f"{vnet_id}/subnets/snet-test"

        mock_client = MagicMock()
        mock_client.virtual_networks.get.return_value = _vnet_object(vnet_id=vnet_id)
        mock_client.subnets.get.return_value = _subnet_object(subnet_id=subnet_id)

        with (
            patch("board.azure.deployment.NetworkManagementClient", return_value=mock_client),
            patch("board.azure.deployment.bicep_build", new_callable=AsyncMock) as bicep_mock,
            patch("board.azure.deployment.deploy", new_callable=AsyncMock) as deploy_mock,
        ):
            result = await ensure_network(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                prefix="test",
                location="australiaeast",
                tags={"environment": "dev"},
                network_bicep_path=Path("/tmp/network.bicep"),
                allowed_ssh_source_ip="*",
            )

        assert result == (vnet_id, subnet_id)
        bicep_mock.assert_not_awaited()
        deploy_mock.assert_not_awaited()
        mock_client.virtual_networks.get.assert_called_once_with("rg-test", "vnet-test")
        mock_client.subnets.get.assert_called_once_with("rg-test", "vnet-test", "snet-test")

    @pytest.mark.asyncio
    async def test_missing_vnet_compiles_and_deploys_network_bicep(self) -> None:
        """When vnet is missing, compile network.bicep and deploy it."""
        from azure.core.exceptions import ResourceNotFoundError

        mock_client = MagicMock()
        mock_client.virtual_networks.get.side_effect = ResourceNotFoundError("vnet not found")

        template_stub = {"$schema": "https://schema.management.azure.com/...", "resources": []}
        deploy_outputs = {"vnetResourceId": "/v", "subnetResourceId": "/s"}

        with (
            patch("board.azure.deployment.NetworkManagementClient", return_value=mock_client),
            patch(
                "board.azure.deployment.bicep_build",
                new_callable=AsyncMock,
                return_value=template_stub,
            ) as bicep_mock,
            patch(
                "board.azure.deployment.deploy",
                new_callable=AsyncMock,
                return_value=deploy_outputs,
            ) as deploy_mock,
        ):
            result = await ensure_network(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                prefix="test",
                location="australiaeast",
                tags={"environment": "dev"},
                network_bicep_path=Path("/tmp/network.bicep"),
                allowed_ssh_source_ip="*",
            )

        assert result == ("/v", "/s")
        bicep_mock.assert_awaited_once_with(Path("/tmp/network.bicep"))
        assert deploy_mock.await_count == 1
        await_args = deploy_mock.await_args
        assert await_args is not None
        assert await_args.kwargs["parameters"] == {
            "prefix": "test",
            "location": "australiaeast",
            "tags": {"environment": "dev"},
            "allowedSshSourceIP": "*",
            "enableDirectHttps": False,
        }
        # Subnet client must not be queried when vnet is missing.
        mock_client.subnets.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_vnet_missing_subnet_raises(self) -> None:
        """If vnet exists but subnet does not, raise BoardError naming both."""
        from azure.core.exceptions import ResourceNotFoundError

        mock_client = MagicMock()
        mock_client.virtual_networks.get.return_value = _vnet_object()
        mock_client.subnets.get.side_effect = ResourceNotFoundError("subnet not found")

        with (
            patch("board.azure.deployment.NetworkManagementClient", return_value=mock_client),
            patch("board.azure.deployment.bicep_build", new_callable=AsyncMock),
            patch("board.azure.deployment.deploy", new_callable=AsyncMock),
            pytest.raises(BoardError) as exc_info,
        ):
            await ensure_network(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                prefix="myprefix",
                location="australiaeast",
                tags={},
                network_bicep_path=Path("/tmp/network.bicep"),
                allowed_ssh_source_ip="*",
            )

        msg = str(exc_info.value)
        assert "vnet-myprefix" in msg
        assert "snet-myprefix" in msg

    @pytest.mark.asyncio
    async def test_existing_vnet_subnet_failed_state_raises(self) -> None:
        """Subnet in non-Succeeded state raises BoardError naming subnet + state."""
        mock_client = MagicMock()
        mock_client.virtual_networks.get.return_value = _vnet_object()
        mock_client.subnets.get.return_value = _subnet_object(state="Failed")

        with (
            patch("board.azure.deployment.NetworkManagementClient", return_value=mock_client),
            patch("board.azure.deployment.bicep_build", new_callable=AsyncMock),
            patch("board.azure.deployment.deploy", new_callable=AsyncMock),
            pytest.raises(BoardError) as exc_info,
        ):
            await ensure_network(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                prefix="myprefix",
                location="australiaeast",
                tags={},
                network_bicep_path=Path("/tmp/network.bicep"),
                allowed_ssh_source_ip="*",
            )

        msg = str(exc_info.value)
        assert "snet-myprefix" in msg
        assert "Failed" in msg

    @pytest.mark.asyncio
    async def test_existing_vnet_in_non_succeeded_state_raises(self) -> None:
        """Vnet in Updating state raises BoardError; subnet must NOT be queried."""
        mock_client = MagicMock()
        mock_client.virtual_networks.get.return_value = _vnet_object(state="Updating")

        with (
            patch("board.azure.deployment.NetworkManagementClient", return_value=mock_client),
            patch("board.azure.deployment.bicep_build", new_callable=AsyncMock),
            patch("board.azure.deployment.deploy", new_callable=AsyncMock),
            pytest.raises(BoardError) as exc_info,
        ):
            await ensure_network(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                prefix="myprefix",
                location="australiaeast",
                tags={},
                network_bicep_path=Path("/tmp/network.bicep"),
                allowed_ssh_source_ip="*",
            )

        msg = str(exc_info.value)
        assert "vnet-myprefix" in msg
        assert "Updating" in msg
        mock_client.subnets.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_tags_and_prefix_passed_through_to_deploy(self) -> None:
        """Tenant-mandated tags are forwarded to deploy() verbatim."""
        from azure.core.exceptions import ResourceNotFoundError

        mock_client = MagicMock()
        mock_client.virtual_networks.get.side_effect = ResourceNotFoundError("vnet not found")

        custom_tags = {"costcenter": "CC-123", "owner": "barney"}

        with (
            patch("board.azure.deployment.NetworkManagementClient", return_value=mock_client),
            patch(
                "board.azure.deployment.bicep_build",
                new_callable=AsyncMock,
                return_value={"resources": []},
            ),
            patch(
                "board.azure.deployment.deploy",
                new_callable=AsyncMock,
                return_value={"vnetResourceId": "/v", "subnetResourceId": "/s"},
            ) as deploy_mock,
        ):
            await ensure_network(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                prefix="myprefix",
                location="australiaeast",
                tags=custom_tags,
                network_bicep_path=Path("/tmp/network.bicep"),
                allowed_ssh_source_ip="*",
            )

        await_args = deploy_mock.await_args
        assert await_args is not None
        params = await_args.kwargs["parameters"]
        assert params["tags"] == {"costcenter": "CC-123", "owner": "barney"}
        assert params["prefix"] == "myprefix"
        assert params["location"] == "australiaeast"

    @pytest.mark.asyncio
    async def test_legacy_subnet_without_nsg_triggers_redeploy(self) -> None:
        """vnet+subnet exist but subnet has no NSG attached → run network.bicep
        once to attach the shared subnet NSG."""
        mock_client = MagicMock()
        mock_client.virtual_networks.get.return_value = _vnet_object()
        mock_client.subnets.get.return_value = _subnet_object(nsg_id=None)

        with (
            patch("board.azure.deployment.NetworkManagementClient", return_value=mock_client),
            patch(
                "board.azure.deployment.bicep_build",
                new_callable=AsyncMock,
                return_value={"resources": []},
            ) as bicep_mock,
            patch(
                "board.azure.deployment.deploy",
                new_callable=AsyncMock,
                return_value={"vnetResourceId": "/v", "subnetResourceId": "/s"},
            ) as deploy_mock,
        ):
            result = await ensure_network(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                prefix="legacy",
                location="australiaeast",
                tags={},
                network_bicep_path=Path("/tmp/network.bicep"),
                allowed_ssh_source_ip="198.51.100.7",
                enable_direct_https=True,
            )

        assert result == ("/v", "/s")
        bicep_mock.assert_awaited_once()
        deploy_mock.assert_awaited_once()
        await_args = deploy_mock.await_args
        assert await_args is not None
        params = await_args.kwargs["parameters"]
        assert params["allowedSshSourceIP"] == "198.51.100.7"
        assert params["enableDirectHttps"] is True

    @pytest.mark.asyncio
    async def test_subnet_with_attached_nsg_uses_early_return(self) -> None:
        """Explicit cover of the happy path: existing subnet has an NSG → no deploy."""
        mock_client = MagicMock()
        mock_client.virtual_networks.get.return_value = _vnet_object()
        mock_client.subnets.get.return_value = _subnet_object()  # nsg_id default = non-empty

        with (
            patch("board.azure.deployment.NetworkManagementClient", return_value=mock_client),
            patch("board.azure.deployment.bicep_build", new_callable=AsyncMock) as bicep_mock,
            patch("board.azure.deployment.deploy", new_callable=AsyncMock) as deploy_mock,
        ):
            await ensure_network(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                prefix="test",
                location="australiaeast",
                tags={},
                network_bicep_path=Path("/tmp/network.bicep"),
                allowed_ssh_source_ip="*",
            )

        bicep_mock.assert_not_awaited()
        deploy_mock.assert_not_awaited()


# ── VM List Parsing Tests ──


class TestListVms:
    @pytest.mark.asyncio
    async def test_list_vms_parses_correctly(self) -> None:
        """Verify VM list parsing extracts power state and metadata."""
        mock_vm = SimpleNamespace(
            name="vm-personal-aue-devvm-jbloggs",
            hardware_profile=SimpleNamespace(vm_size="Standard_D4s_v5"),
            storage_profile=SimpleNamespace(
                os_disk=SimpleNamespace(os_type="Linux"),
            ),
            location="australiaeast",
            tags={"project": "devvm", "owner": "jbloggs"},
        )
        mock_instance_view = SimpleNamespace(
            statuses=[
                SimpleNamespace(code="ProvisioningState/succeeded"),
                SimpleNamespace(code="PowerState/running"),
            ],
        )

        mock_client = MagicMock()
        mock_client.virtual_machines.list.return_value = [mock_vm]
        mock_client.virtual_machines.instance_view.return_value = mock_instance_view

        with patch(
            "board.azure.compute.ComputeManagementClient",
            return_value=mock_client,
        ):
            vms = await list_vms(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
            )

        assert len(vms) == 1
        assert vms[0]["name"] == "vm-personal-aue-devvm-jbloggs"
        assert vms[0]["vm_size"] == "Standard_D4s_v5"
        assert vms[0]["os"] == "Linux"
        assert vms[0]["power_state"] == "running"
        assert vms[0]["location"] == "australiaeast"

    @pytest.mark.asyncio
    async def test_list_vms_empty(self) -> None:
        """Empty resource group returns empty list."""
        mock_client = MagicMock()
        mock_client.virtual_machines.list.return_value = []

        with patch(
            "board.azure.compute.ComputeManagementClient",
            return_value=mock_client,
        ):
            vms = await list_vms(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-empty",
            )

        assert vms == []

    @pytest.mark.asyncio
    async def test_list_vms_unknown_power_state(self) -> None:
        """VM with no PowerState status should report 'unknown'."""
        mock_vm = SimpleNamespace(
            name="vm-test",
            hardware_profile=SimpleNamespace(vm_size="Standard_B1s"),
            storage_profile=SimpleNamespace(
                os_disk=SimpleNamespace(os_type="Linux"),
            ),
            location="eastus",
            tags=None,
        )
        mock_instance_view = SimpleNamespace(
            statuses=[
                SimpleNamespace(code="ProvisioningState/succeeded"),
            ],
        )

        mock_client = MagicMock()
        mock_client.virtual_machines.list.return_value = [mock_vm]
        mock_client.virtual_machines.instance_view.return_value = mock_instance_view

        with patch(
            "board.azure.compute.ComputeManagementClient",
            return_value=mock_client,
        ):
            vms = await list_vms(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
            )

        assert vms[0]["power_state"] == "unknown"


# ── Deployment Tests ──

# Store real asyncio.sleep BEFORE any patching so our yielding mock can use it.
_real_sleep = asyncio.sleep


async def _instant_sleep(_seconds: float) -> None:
    """Replacement for asyncio.sleep that yields to the event loop without waiting."""
    await _real_sleep(0)


def _mock_poller_async(result_value: object) -> MagicMock:
    """Create a mock async LRO poller.

    The deploy() function calls ``asyncio.create_task(poller.result())``
    so ``result`` must be an async callable returning a coroutine.
    """
    poller = MagicMock()
    poller.result = AsyncMock(return_value=result_value)
    return poller


def _deployment_result(outputs: dict | None = None) -> SimpleNamespace:
    """Create a mock DeploymentExtended result."""
    out = {}
    if outputs:
        out = {k: {"value": v} for k, v in outputs.items()}
    return SimpleNamespace(
        properties=SimpleNamespace(outputs=out),
    )


class TestDeployment:
    @pytest.mark.asyncio
    async def test_deploy_sdk_success(self) -> None:
        """Deploy succeeds and returns extracted outputs."""
        result = _deployment_result({"publicIpAddress": "1.2.3.4"})
        poller = _mock_poller_async(result)

        mock_client = MagicMock()
        mock_client.deployments.begin_create_or_update = AsyncMock(return_value=poller)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("board.azure.deployment.DeploymentsMgmtClient", return_value=mock_client):
            outputs = await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={"$schema": "..."},
                parameters={"developerName": "jbloggs", "vmSku": "Standard_D2s_v6"},
                deployment_name="test-deploy",
            )

        assert outputs == {"publicIpAddress": "1.2.3.4"}
        mock_client.deployments.begin_create_or_update.assert_awaited_once()

        # Verify ARM parameter wrapping
        call_args = mock_client.deployments.begin_create_or_update.call_args
        deployment_obj = call_args[0][2]
        params = deployment_obj.properties.parameters
        assert params["developerName"] == {"value": "jbloggs"}
        assert params["vmSku"] == {"value": "Standard_D2s_v6"}

    @pytest.mark.asyncio
    async def test_deploy_sdk_timeout(self) -> None:
        """Deploy raises DeploymentError after timeout."""
        import asyncio as _asyncio

        async def _hang_forever():
            await _asyncio.Event().wait()

        poller = MagicMock()
        poller.result = _hang_forever

        mock_client = MagicMock()
        mock_client.deployments.begin_create_or_update = AsyncMock(return_value=poller)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("board.azure.deployment.DeploymentsMgmtClient", return_value=mock_client),
            patch("board.azure.deployment.asyncio.sleep", side_effect=_instant_sleep),
            patch("board.azure.deployment.time.monotonic", side_effect=[0] * 20 + [9999] * 20),
            pytest.raises(DeploymentError, match="timed out"),
        ):
            await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
                deployment_name="test-deploy",
                timeout=60,
            )

    @pytest.mark.asyncio
    async def test_deploy_sdk_failure(self) -> None:
        """Deploy raises DeploymentError when SDK throws."""
        mock_client = MagicMock()
        mock_client.deployments.begin_create_or_update = AsyncMock(
            side_effect=Exception("ARM validation error")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("board.azure.deployment.DeploymentsMgmtClient", return_value=mock_client),
            pytest.raises(DeploymentError, match="failed to start"),
        ):
            await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
            )

    @pytest.mark.asyncio
    async def test_deploy_progress_callback(self) -> None:
        """Deploy calls on_progress for each resource state change."""
        result = _deployment_result({"ip": "1.2.3.4"})
        poller = _mock_poller_async(result)

        mock_op = SimpleNamespace(
            target_resource=SimpleNamespace(resource_type="Microsoft.Network/publicIPAddresses"),
            provisioning_state="Succeeded",
        )

        async def _mock_list(*_args: object, **_kwargs: object):  # noqa: ANN202
            yield mock_op

        mock_client = MagicMock()
        mock_client.deployments.begin_create_or_update = AsyncMock(return_value=poller)
        mock_client.deployment_operations.list = _mock_list
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        progress_calls: list[tuple[str, str]] = []

        def on_progress(resource: str, state: str) -> None:
            progress_calls.append((resource, state))

        with (
            patch("board.azure.deployment.DeploymentsMgmtClient", return_value=mock_client),
            patch("board.azure.deployment.asyncio.sleep", side_effect=_instant_sleep),
            patch("board.azure.deployment.time.monotonic", return_value=0),
        ):
            await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
                deployment_name="test-deploy",
                on_progress=on_progress,
            )

        assert ("publicIPAddresses", "Succeeded") in progress_calls

    @pytest.mark.asyncio
    async def test_bicep_build_delegates_to_az_text(self) -> None:
        """bicep_build calls az_text with correct args."""
        with patch(
            "board.azure.deployment.az_text",
            new_callable=AsyncMock,
            return_value='{"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"}',
        ) as mock_az:
            from pathlib import Path

            result = await bicep_build(Path("/tmp/main.bicep"))

        assert result["$schema"].startswith("https://schema.management.azure.com")
        mock_az.assert_awaited_once_with(
            "bicep", "build", "--file", "/tmp/main.bicep", "--stdout", timeout=60
        )
