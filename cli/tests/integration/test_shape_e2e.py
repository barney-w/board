"""End-to-end integration tests for the Shape step deployment pipeline.

Exercises the full call chain from setup.py through deployment.py/auth.py/az.py
with mocks at the Azure SDK and subprocess boundaries. No real Azure calls.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from board.azure.auth import get_credential, get_subscription_id, get_tenant_id, list_subscriptions
from board.azure.az import az_json, az_text
from board.azure.deployment import bicep_build, deploy
from board.core.errors import BoardError, DeploymentError

# Store real sleep before any patching so yielding mock can use it.
_real_sleep = asyncio.sleep


async def _instant_sleep(_seconds: float) -> None:
    """Replacement for asyncio.sleep that yields to the event loop without waiting."""
    await _real_sleep(0)


# ── Bicep parameter cross-check ──


class TestBicepParameterNames:
    """Verify the parameter names used in code match the Bicep template exactly."""

    @pytest.fixture
    def bicep_source(self) -> str:
        """Read the actual main.bicep file."""
        # Walk up from tests/ to repo root, then into infra/
        repo_root = Path(__file__).resolve().parents[3]
        bicep_path = repo_root / "infra" / "main.bicep"
        if not bicep_path.exists():
            pytest.skip("main.bicep not found (running outside full repo)")
        return bicep_path.read_text()

    def _extract_param_names(self, bicep_source: str) -> set[str]:
        """Extract param names from Bicep source."""
        import re

        return set(re.findall(r"^param\s+(\w+)\s", bicep_source, re.MULTILINE))

    def test_setup_params_exist_in_bicep(self, bicep_source: str) -> None:
        """The parameter names used in setup.py must exist in main.bicep."""
        bicep_params = self._extract_param_names(bicep_source)

        # These are the params setup.py passes to deploy()
        setup_params = {"developerName", "vmSku", "adminSshPublicKey", "environment"}
        missing = setup_params - bicep_params
        assert not missing, f"setup.py passes params not in main.bicep: {missing}"

    def test_infra_params_exist_in_bicep(self, bicep_source: str) -> None:
        """The parameter names used in infra.py create_vm_command must exist in main.bicep."""
        bicep_params = self._extract_param_names(bicep_source)

        # These are the params infra.py passes via CLI --parameters
        infra_params = {"developerName", "vmSku", "adminSshPublicKey"}
        missing = infra_params - bicep_params
        assert not missing, f"infra.py passes params not in main.bicep: {missing}"

    def test_required_params_all_passed(self, bicep_source: str) -> None:
        """Every required Bicep param (no default) must be passed by setup.py."""
        import re

        # A required param looks like: param developerName string
        # A param with default looks like: param vmSku string = 'Standard_D2s_v6'
        all_params = re.findall(r"^param\s+(\w+)\s+\w+\s*$", bicep_source, re.MULTILINE)
        # Exclude @secure() params that are on a separate line
        secure_params = re.findall(r"@secure\(\)\s*\n\s*param\s+(\w+)\s+\w+", bicep_source)
        required = set(all_params) | set(secure_params)

        setup_provides = {"developerName", "vmSku", "adminSshPublicKey", "environment"}
        missing = required - setup_provides
        assert not missing, (
            f"Bicep requires params not provided by setup.py: {missing}. "
            f"Required: {required}, Provided: {setup_provides}"
        )


# ── az.py integration ──


class TestAzModuleIntegration:
    """Test az.py with realistic subprocess mocking."""

    @pytest.mark.asyncio
    async def test_az_text_full_lifecycle(self) -> None:
        """Exercise the full az_text path including process creation and cleanup."""
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"sub-abc-123\n", b""))
        proc.returncode = 0

        with patch("board.azure.az.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            result = await az_text("account", "show", "--query", "id", "-o", "tsv")

        assert result == "sub-abc-123"

    @pytest.mark.asyncio
    async def test_az_json_full_lifecycle(self) -> None:
        """Exercise az_json with realistic JSON response."""
        accounts = [
            {"name": "Dev Sub", "id": "sub-123", "isDefault": True},
            {"name": "Prod Sub", "id": "sub-456", "isDefault": False},
        ]
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(json.dumps(accounts).encode(), b""))
        proc.returncode = 0

        with patch("board.azure.az.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            result = await az_json("account", "list", "-o", "json")

        assert len(result) == 2
        assert result[0]["id"] == "sub-123"

    @pytest.mark.asyncio
    async def test_az_text_timeout_cleans_up_process(self) -> None:
        """On timeout, process must be killed AND waited for (no zombies)."""
        proc = MagicMock()
        proc.communicate = AsyncMock(side_effect=TimeoutError)
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        with (
            patch("board.azure.az.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
            pytest.raises(BoardError, match="timed out"),
        ):
            await az_text("deployment", "group", "create", timeout=1)

        proc.kill.assert_called_once()
        proc.wait.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_az_text_stderr_in_error_message(self) -> None:
        """Error messages must include stderr for debugging."""
        proc = MagicMock()
        proc.communicate = AsyncMock(
            return_value=(b"", b"ERROR: The client 'x@y.com' does not have authorization")
        )
        proc.returncode = 1

        with (
            patch("board.azure.az.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
            pytest.raises(BoardError, match="does not have authorization"),
        ):
            await az_text("deployment", "group", "create")


# ── Auth module integration ──


class TestAuthIntegration:
    @pytest.mark.asyncio
    async def test_get_subscription_id_from_env(self) -> None:
        """Environment variable takes priority over az CLI."""
        with patch.dict("os.environ", {"AZURE_SUBSCRIPTION_ID": "env-sub-123"}):
            result = await get_subscription_id()
        assert result == "env-sub-123"

    @pytest.mark.asyncio
    async def test_get_subscription_id_from_board_env(self) -> None:
        """BOARD_SUBSCRIPTION_ID works as alternative."""
        with patch.dict(
            "os.environ",
            {"BOARD_SUBSCRIPTION_ID": "board-sub-456"},
            clear=False,
        ):
            # Clear AZURE_SUBSCRIPTION_ID if set
            import os

            os.environ.pop("AZURE_SUBSCRIPTION_ID", None)
            result = await get_subscription_id()
        assert result == "board-sub-456"

    @pytest.mark.asyncio
    async def test_get_subscription_id_falls_back_to_cli(self) -> None:
        """When no env var set, falls back to az CLI."""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "board.azure.auth.az_text",
                new_callable=AsyncMock,
                return_value="cli-sub-789",
            ),
        ):
            result = await get_subscription_id()
        assert result == "cli-sub-789"

    @pytest.mark.asyncio
    async def test_get_subscription_id_empty_cli_raises(self) -> None:
        """Empty az CLI result raises RuntimeError."""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "board.azure.auth.az_text",
                new_callable=AsyncMock,
                return_value="",
            ),
            pytest.raises(RuntimeError, match="No Azure subscription"),
        ):
            await get_subscription_id()

    @pytest.mark.asyncio
    async def test_get_tenant_id_calls_az(self) -> None:
        """get_tenant_id delegates to az_text."""
        with patch(
            "board.azure.auth.az_text",
            new_callable=AsyncMock,
            return_value="tenant-abc-123",
        ) as mock_az:
            result = await get_tenant_id()

        assert result == "tenant-abc-123"
        mock_az.assert_awaited_once_with(
            "account", "show", "--query", "tenantId", "-o", "tsv", timeout=30
        )

    @pytest.mark.asyncio
    async def test_list_subscriptions_parses_correctly(self) -> None:
        """list_subscriptions transforms az output to list of dicts."""
        with patch(
            "board.azure.auth.az_json",
            new_callable=AsyncMock,
            return_value=[
                ["My Dev", "sub-111", True],
                ["My Prod", "sub-222", False],
            ],
        ):
            result = await list_subscriptions()

        assert len(result) == 2
        assert result[0] == {"name": "My Dev", "id": "sub-111", "is_default": True}
        assert result[1] == {"name": "My Prod", "id": "sub-222", "is_default": False}

    def test_get_credential_returns_dac(self) -> None:
        """get_credential returns a DefaultAzureCredential."""
        cred = get_credential()
        assert cred is not None
        assert type(cred).__name__ == "DefaultAzureCredential"


# ── Deploy integration (full SDK flow) ──


def _make_deployment_result(outputs: dict | None = None) -> SimpleNamespace:
    """Create a realistic DeploymentExtended mock."""
    out = {}
    if outputs:
        out = {k: {"value": v, "type": "String"} for k, v in outputs.items()}
    return SimpleNamespace(
        properties=SimpleNamespace(
            outputs=out,
            provisioning_state="Succeeded",
        ),
    )


def _make_sdk_client(
    poller_result: object,
    operations: list[object] | None = None,
    start_error: Exception | None = None,
) -> MagicMock:
    """Create a fully wired mock DeploymentsMgmtClient."""
    poller = MagicMock()
    poller.result = AsyncMock(return_value=poller_result)

    client = MagicMock()
    if start_error:
        client.deployments.begin_create_or_update = AsyncMock(side_effect=start_error)
    else:
        client.deployments.begin_create_or_update = AsyncMock(return_value=poller)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    if operations:

        async def _list(*_a: object, **_kw: object):  # noqa: ANN202
            for op in operations:
                yield op

        client.deployment_operations.list = _list

    return client


class TestDeployIntegration:
    """Full deploy() flow tests with realistic mocking."""

    @pytest.mark.asyncio
    async def test_deploy_with_all_setup_params(self) -> None:
        """Test deploy() with the exact parameters setup.py passes."""
        result = _make_deployment_result(
            {
                "publicIpAddress": "20.1.2.3",
                "fqdn": "vm-personal-aue-devvm-jbloggs.australiaeast.cloudapp.azure.com",
            }
        )
        client = _make_sdk_client(result)

        with patch("board.azure.deployment.DeploymentsMgmtClient", return_value=client):
            outputs = await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-personal-aue-devvm",
                template={
                    "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
                },
                parameters={
                    "developerName": "jbloggs",
                    "vmSku": "Standard_D2s_v6",
                    "adminSshPublicKey": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKey",
                    "environment": "personal",
                },
                deployment_name="board-jbloggs-1711792800",
            )

        assert outputs["publicIpAddress"] == "20.1.2.3"
        assert "fqdn" in outputs

        # Verify SDK was called with correctly wrapped ARM params
        call_args = client.deployments.begin_create_or_update.call_args
        deployment_obj = call_args[0][2]  # 3rd positional arg = Deployment
        arm_params = deployment_obj.properties.parameters

        assert arm_params["developerName"] == {"value": "jbloggs"}
        assert arm_params["vmSku"] == {"value": "Standard_D2s_v6"}
        assert arm_params["adminSshPublicKey"] == {
            "value": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKey"
        }
        assert arm_params["environment"] == {"value": "personal"}

    @pytest.mark.asyncio
    async def test_deploy_with_kv_resource_id(self) -> None:
        """Test deploy() handles optional keyVaultResourceId parameter."""
        result = _make_deployment_result({"publicIpAddress": "10.0.0.1"})
        client = _make_sdk_client(result)

        with patch("board.azure.deployment.DeploymentsMgmtClient", return_value=client):
            await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
                parameters={
                    "developerName": "jbloggs",
                    "vmSku": "Standard_D2s_v6",
                    "adminSshPublicKey": "ssh-ed25519 AAAA...",
                    "environment": "personal",
                    "keyVaultResourceId": "/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.KeyVault/vaults/kv-test",
                },
            )

        call_args = client.deployments.begin_create_or_update.call_args
        arm_params = call_args[0][2].properties.parameters
        assert "keyVaultResourceId" in arm_params
        assert arm_params["keyVaultResourceId"]["value"].startswith("/subscriptions/")

    @pytest.mark.asyncio
    async def test_deploy_pre_wrapped_params_not_double_wrapped(self) -> None:
        """Parameters already in ARM format should not be double-wrapped."""
        result = _make_deployment_result({})
        client = _make_sdk_client(result)

        with patch("board.azure.deployment.DeploymentsMgmtClient", return_value=client):
            await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
                parameters={
                    "raw": "plain-value",
                    "wrapped": {"value": "already-wrapped"},
                },
            )

        call_args = client.deployments.begin_create_or_update.call_args
        arm_params = call_args[0][2].properties.parameters
        assert arm_params["raw"] == {"value": "plain-value"}
        assert arm_params["wrapped"] == {"value": "already-wrapped"}

    @pytest.mark.asyncio
    async def test_deploy_progress_multiple_resources(self) -> None:
        """Progress callback fires for each unique resource state transition."""
        result = _make_deployment_result({"ip": "1.2.3.4"})
        operations = [
            SimpleNamespace(
                target_resource=SimpleNamespace(
                    resource_type="Microsoft.Network/networkSecurityGroups"
                ),
                provisioning_state="Succeeded",
            ),
            SimpleNamespace(
                target_resource=SimpleNamespace(resource_type="Microsoft.Network/virtualNetworks"),
                provisioning_state="Creating",
            ),
            SimpleNamespace(
                target_resource=SimpleNamespace(resource_type="Microsoft.Compute/virtualMachines"),
                provisioning_state="Running",
            ),
        ]
        client = _make_sdk_client(
            result,
            operations=operations,
        )

        progress: list[tuple[str, str]] = []

        with (
            patch("board.azure.deployment.DeploymentsMgmtClient", return_value=client),
            patch("board.azure.deployment.asyncio.sleep", side_effect=_instant_sleep),
            patch("board.azure.deployment.time.monotonic", return_value=0),
        ):
            await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
                deployment_name="test-deploy",
                on_progress=lambda r, s: progress.append((r, s)),
            )

        resource_names = [r for r, _ in progress]
        assert "networkSecurityGroups" in resource_names
        assert "virtualNetworks" in resource_names
        assert "virtualMachines" in resource_names

    @pytest.mark.asyncio
    async def test_deploy_progress_deduplicates(self) -> None:
        """Same resource+state should only be reported once."""
        result = _make_deployment_result({})
        same_op = SimpleNamespace(
            target_resource=SimpleNamespace(resource_type="Microsoft.Network/virtualNetworks"),
            provisioning_state="Creating",
        )
        client = _make_sdk_client(
            result,
            operations=[same_op],
        )

        progress: list[tuple[str, str]] = []

        with (
            patch("board.azure.deployment.DeploymentsMgmtClient", return_value=client),
            patch("board.azure.deployment.asyncio.sleep", side_effect=_instant_sleep),
            patch("board.azure.deployment.time.monotonic", return_value=0),
        ):
            await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
                deployment_name="test",
                on_progress=lambda r, s: progress.append((r, s)),
            )

        # Should only appear once despite two polling iterations
        vnet_calls = [(r, s) for r, s in progress if r == "virtualNetworks"]
        assert len(vnet_calls) == 1

    @pytest.mark.asyncio
    async def test_deploy_no_params(self) -> None:
        """Deploy with no parameters works (template with all defaults)."""
        result = _make_deployment_result({})
        client = _make_sdk_client(result)

        with patch("board.azure.deployment.DeploymentsMgmtClient", return_value=client):
            outputs = await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
            )

        assert outputs == {}
        call_args = client.deployments.begin_create_or_update.call_args
        assert call_args[0][2].properties.parameters is None

    @pytest.mark.asyncio
    async def test_deploy_auto_generates_name(self) -> None:
        """When no deployment_name given, one is auto-generated."""
        result = _make_deployment_result({})
        client = _make_sdk_client(result)

        with patch("board.azure.deployment.DeploymentsMgmtClient", return_value=client):
            await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
            )

        call_args = client.deployments.begin_create_or_update.call_args
        name = call_args[0][1]  # 2nd positional arg = deployment name
        assert name.startswith("board-")

    @pytest.mark.asyncio
    async def test_deploy_timeout_includes_deployment_name(self) -> None:
        """Timeout error includes deployment name for portal debugging."""

        async def _hang_forever():
            await asyncio.Event().wait()

        poller = MagicMock()
        poller.result = _hang_forever

        client = MagicMock()
        client.deployments.begin_create_or_update = AsyncMock(return_value=poller)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("board.azure.deployment.DeploymentsMgmtClient", return_value=client),
            patch("board.azure.deployment.asyncio.sleep", side_effect=_instant_sleep),
            patch("board.azure.deployment.time.monotonic", side_effect=[0] * 20 + [9999] * 20),
            pytest.raises(DeploymentError, match="board-jbloggs-test"),
        ):
            await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
                deployment_name="board-jbloggs-test",
                timeout=60,
            )

    @pytest.mark.asyncio
    async def test_deploy_sdk_exception_wraps_in_deployment_error(self) -> None:
        """Azure SDK exceptions are wrapped in DeploymentError."""
        client = _make_sdk_client(None, start_error=Exception("InvalidTemplate: ..."))

        with (
            patch("board.azure.deployment.DeploymentsMgmtClient", return_value=client),
            pytest.raises(DeploymentError, match="failed to start.*InvalidTemplate"),
        ):
            await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
            )

    @pytest.mark.asyncio
    async def test_deploy_result_extraction(self) -> None:
        """Outputs are correctly extracted from nested ARM format."""
        result = _make_deployment_result(
            {
                "publicIpAddress": "20.1.2.3",
                "fqdn": "vm.australiaeast.cloudapp.azure.com",
                "sshCommand": "ssh devuser@vm.australiaeast.cloudapp.azure.com",
            }
        )
        client = _make_sdk_client(result)

        with patch("board.azure.deployment.DeploymentsMgmtClient", return_value=client):
            outputs = await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
            )

        assert outputs["publicIpAddress"] == "20.1.2.3"
        assert outputs["fqdn"] == "vm.australiaeast.cloudapp.azure.com"
        assert outputs["sshCommand"] == "ssh devuser@vm.australiaeast.cloudapp.azure.com"

    @pytest.mark.asyncio
    async def test_deploy_empty_outputs(self) -> None:
        """Deploy with no outputs returns empty dict."""
        result = SimpleNamespace(properties=SimpleNamespace(outputs=None))
        client = _make_sdk_client(result)

        with patch("board.azure.deployment.DeploymentsMgmtClient", return_value=client):
            outputs = await deploy(
                credential=MagicMock(),
                subscription_id="sub-123",
                resource_group="rg-test",
                template={},
            )

        assert outputs == {}


# ── Bicep build integration ──


class TestBicepBuildIntegration:
    @pytest.mark.asyncio
    async def test_bicep_build_returns_parsed_template(self) -> None:
        """bicep_build returns parsed JSON from az bicep build."""
        template = {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "1.0.0.0",
            "parameters": {"developerName": {"type": "string"}},
            "resources": [],
        }
        with patch(
            "board.azure.deployment.az_text",
            new_callable=AsyncMock,
            return_value=json.dumps(template),
        ):
            result = await bicep_build(Path("/fake/main.bicep"))

        assert result["parameters"]["developerName"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_bicep_build_failure_wraps_error(self) -> None:
        """az CLI failure is wrapped in DeploymentError."""
        with (
            patch(
                "board.azure.deployment.az_text",
                new_callable=AsyncMock,
                side_effect=BoardError("az bicep failed: BCP001 syntax error"),
            ),
            pytest.raises(DeploymentError, match="Bicep compilation failed.*BCP001"),
        ):
            await bicep_build(Path("/fake/bad.bicep"))

    @pytest.mark.asyncio
    async def test_bicep_build_invalid_json(self) -> None:
        """Non-JSON output from az bicep build raises DeploymentError."""
        with (
            patch(
                "board.azure.deployment.az_text",
                new_callable=AsyncMock,
                return_value="WARNING: Some deprecation notice\n{not json}",
            ),
            pytest.raises(DeploymentError, match="not valid JSON"),
        ):
            await bicep_build(Path("/fake/main.bicep"))
