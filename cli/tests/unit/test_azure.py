"""Tests for Azure modules — Key Vault state machine, resource groups, VM parsing.

All Azure SDK clients are mocked. No real Azure calls are made.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from board.azure.compute import list_vms
from board.azure.deployment import bicep_build, deploy, ensure_resource_group
from board.azure.keyvault import (
    create_or_recover_vault,
    get_secret,
    list_secrets,
    set_secret,
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


# ── Resource Group Tests ──


class TestEnsureResourceGroup:
    @pytest.mark.asyncio
    async def test_rg_already_exists(self) -> None:
        """If RG exists and is Succeeded, do nothing."""
        mock_client = MagicMock()
        mock_client.resource_groups.check_existence.return_value = True
        mock_client.resource_groups.get.return_value = SimpleNamespace(
            properties=SimpleNamespace(provisioning_state="Succeeded"),
        )

        with patch(
            "board.azure.deployment.ResourceManagementClient",
            return_value=mock_client,
        ):
            await ensure_resource_group(
                credential=MagicMock(),
                subscription_id="sub-123",
                name="rg-test",
                location="australiaeast",
            )

        mock_client.resource_groups.create_or_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_rg_does_not_exist_creates(self) -> None:
        """If RG doesn't exist, create it."""
        mock_client = MagicMock()
        mock_client.resource_groups.check_existence.return_value = False

        with patch(
            "board.azure.deployment.ResourceManagementClient",
            return_value=mock_client,
        ):
            await ensure_resource_group(
                credential=MagicMock(),
                subscription_id="sub-123",
                name="rg-new",
                location="australiaeast",
            )

        mock_client.resource_groups.create_or_update.assert_called_once()
        call_args = mock_client.resource_groups.create_or_update.call_args
        assert call_args[0][0] == "rg-new"
        assert call_args[0][1]["location"] == "australiaeast"

    @pytest.mark.asyncio
    async def test_rg_deleting_raises(self) -> None:
        """If RG is in Deleting state, raise DeploymentError."""
        mock_client = MagicMock()
        mock_client.resource_groups.check_existence.return_value = True
        mock_client.resource_groups.get.return_value = SimpleNamespace(
            properties=SimpleNamespace(provisioning_state="Deleting"),
        )

        with (
            patch(
                "board.azure.deployment.ResourceManagementClient",
                return_value=mock_client,
            ),
            pytest.raises(DeploymentError, match="being deleted"),
        ):
            await ensure_resource_group(
                credential=MagicMock(),
                subscription_id="sub-123",
                name="rg-test",
                location="australiaeast",
            )

    @pytest.mark.asyncio
    async def test_rg_failed_state_raises(self) -> None:
        """If RG is in a failed state, raise DeploymentError."""
        mock_client = MagicMock()
        mock_client.resource_groups.check_existence.return_value = True
        mock_client.resource_groups.get.return_value = SimpleNamespace(
            properties=SimpleNamespace(provisioning_state="Failed"),
        )

        with (
            patch(
                "board.azure.deployment.ResourceManagementClient",
                return_value=mock_client,
            ),
            pytest.raises(DeploymentError, match="state 'Failed'"),
        ):
            await ensure_resource_group(
                credential=MagicMock(),
                subscription_id="sub-123",
                name="rg-test",
                location="australiaeast",
            )


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
