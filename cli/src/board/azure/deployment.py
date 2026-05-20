"""Bicep compilation and ARM template deployment."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from azure.core.exceptions import ResourceNotFoundError
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.resource.deployments.aio import DeploymentsMgmtClient
from azure.mgmt.resource.deployments.models import (
    Deployment,
    DeploymentMode,
    DeploymentProperties,
)

from board.azure.az import az_text
from board.core.errors import BoardError, DeploymentError

# Built-in role definition GUIDs (stable across all Azure tenants).
# https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles
_OWNER_ROLE_ID = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"
_CONTRIBUTOR_ROLE_ID = "b24988ac-6180-42a0-ab88-20f7382dd24c"
_DEPLOY_ROLE_IDS = (_OWNER_ROLE_ID, _CONTRIBUTOR_ROLE_ID)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


async def bicep_build(bicep_path: Path) -> dict[str, Any]:
    """Compile a Bicep file to ARM JSON via ``az bicep build --stdout``.

    Args:
        bicep_path: Path to the .bicep file.

    Returns:
        Parsed ARM template as a dict.

    Raises:
        DeploymentError: If compilation fails.
    """
    try:
        raw = await az_text("bicep", "build", "--file", str(bicep_path), "--stdout", timeout=60)
    except Exception as exc:
        msg = f"Bicep compilation failed for {bicep_path}: {exc}"
        raise DeploymentError(msg) from exc
    try:
        return json.loads(raw)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        msg = f"Bicep output is not valid JSON: {exc}"
        raise DeploymentError(msg) from exc


async def deploy(
    credential: Any,
    subscription_id: str,
    resource_group: str,
    template: dict[str, Any],
    parameters: dict[str, Any] | None = None,
    deployment_name: str = "",
    on_progress: Callable[[str, str], None] | None = None,
    timeout: int = 1200,
) -> dict[str, Any]:
    """Deploy an ARM template using the Azure SDK.

    Args:
        credential: Azure credential object (used for SDK auth).
        subscription_id: Target subscription.
        resource_group: Target resource group.
        template: ARM template dict (from bicep_build or loaded JSON).
        parameters: Optional parameters dict. Values are auto-wrapped in
            ARM ``{"value": ...}`` format if needed.
        deployment_name: Optional name; auto-generated if empty.
        on_progress: Callback ``(resource_type, state)`` for per-resource updates.
        timeout: Maximum seconds to wait for deployment (default 1200).

    Returns:
        Deployment outputs as a dict.

    Raises:
        DeploymentError: If the deployment fails or times out.
    """
    if not deployment_name:
        deployment_name = f"board-{int(time.time())}"

    # Wrap raw parameter values in ARM format if needed
    arm_params: dict[str, Any] | None = None
    if parameters:
        arm_params = {}
        for k, v in parameters.items():
            if isinstance(v, dict) and "value" in v:
                arm_params[k] = v
            else:
                arm_params[k] = {"value": v}

    async with DeploymentsMgmtClient(credential, subscription_id) as client:
        try:
            poller = await client.deployments.begin_create_or_update(
                resource_group,
                deployment_name,
                Deployment(
                    properties=DeploymentProperties(
                        template=template,
                        parameters=arm_params,
                        mode=DeploymentMode.INCREMENTAL,
                    )
                ),
            )
        except Exception as exc:
            msg = f"Deployment '{deployment_name}' failed to start: {exc}"
            raise DeploymentError(msg) from exc

        # Let the SDK drive polling via result(); report progress alongside it
        result_task = asyncio.create_task(poller.result())
        start = time.monotonic()
        seen: dict[str, str] = {}

        while not result_task.done():
            if time.monotonic() - start > timeout:
                result_task.cancel()
                msg = (
                    f"Deployment '{deployment_name}' timed out after {timeout}s. "
                    f"Check in Azure Portal: resource group '{resource_group}'"
                )
                raise DeploymentError(msg)

            # Report per-resource progress
            if on_progress:
                try:
                    async for op in client.deployment_operations.list(
                        resource_group, deployment_name
                    ):
                        target = getattr(op, "target_resource", None)
                        state = getattr(op, "provisioning_state", None)
                        if target and state:
                            rt = getattr(target, "resource_type", "")
                            short = rt.split("/")[-1] if rt else ""
                            if short and seen.get(short) != state:
                                seen[short] = state
                                on_progress(short, state)
                except Exception:
                    pass  # Progress reporting is best-effort

            await asyncio.sleep(5)

        try:
            result = result_task.result()
        except Exception as exc:
            msg = f"Deployment '{deployment_name}' failed: {exc}"
            raise DeploymentError(msg) from exc

    # Extract outputs
    outputs: dict[str, Any] = {}
    if result and result.properties and result.properties.outputs:
        for key, val in result.properties.outputs.items():
            outputs[key] = val.get("value", val) if isinstance(val, dict) else val
    return outputs


async def verify_resource_group(
    credential: Any,
    subscription_id: str,
    name: str,
    principal_id: str,
) -> tuple[str, dict[str, str]]:
    """Confirm the resource group exists and the caller can deploy to it.

    Board never creates resource groups — they must be provisioned out-of-band
    by a platform team. This helper fails loud if the RG is missing or if the
    caller lacks Contributor / Owner on it.

    Args:
        credential: Azure credential object.
        subscription_id: Target subscription.
        name: Resource group name.
        principal_id: Object ID of the signed-in user, used for the role check.

    Returns:
        Tuple of ``(location, tags)`` from the existing RG. Tags is an empty
        dict if the RG has none.

    Raises:
        BoardError: RG missing, in a bad provisioning state, or the caller
            does not have Contributor or higher on it.
    """
    client = ResourceManagementClient(credential, subscription_id)

    try:
        exists = await asyncio.to_thread(client.resource_groups.check_existence, name)
    except Exception as exc:
        msg = f"Failed to check resource group '{name}': {exc}"
        raise BoardError(msg) from exc

    if not exists:
        msg = (
            f"Resource group '{name}' not found in subscription {subscription_id}. "
            "Create it manually first (or pick another)."
        )
        raise BoardError(msg)

    rg = await asyncio.to_thread(client.resource_groups.get, name)
    state = rg.properties.provisioning_state if rg.properties else None
    if state == "Deleting":
        msg = (
            f"Resource group '{name}' is being deleted. "
            "Wait for deletion to complete or pick another."
        )
        raise BoardError(msg)
    if state and state not in ("Succeeded", "Updating"):
        msg = f"Resource group '{name}' is in state '{state}'. Cannot deploy."
        raise BoardError(msg)

    # Permission check: caller must have Contributor or Owner on the RG.
    if not principal_id:
        msg = (
            "Could not resolve the signed-in user. Run 'az login' as a user "
            "account (not a service principal) and retry."
        )
        raise BoardError(msg)

    auth_client = AuthorizationManagementClient(credential, subscription_id)
    rg_scope = f"/subscriptions/{subscription_id}/resourceGroups/{name}"

    try:
        assignments = await asyncio.to_thread(
            lambda: list(
                auth_client.role_assignments.list_for_scope(
                    scope=rg_scope,
                    filter=f"atScope() and assignedTo('{principal_id}')",
                ),
            ),
        )
    except Exception as exc:
        msg = (
            f"Failed to list role assignments on '{name}': {exc}. "
            "Confirm you have at least Reader on the resource group."
        )
        raise BoardError(msg) from exc

    has_deploy_role = any(
        (rid := getattr(a, "role_definition_id", None))
        and rid.rsplit("/", 1)[-1] in _DEPLOY_ROLE_IDS
        for a in assignments
    )
    if not has_deploy_role:
        msg = (
            f"You don't have Contributor or Owner on resource group '{name}'. "
            "Ask a subscription admin to grant you one of those roles, then retry."
        )
        raise BoardError(msg)

    location = rg.location or ""
    tags = dict(rg.tags) if rg.tags else {}
    return location, tags


async def ensure_network(
    credential: Any,
    subscription_id: str,
    resource_group: str,
    prefix: str,
    location: str,
    tags: dict[str, str],
    network_bicep_path: Path,
    allowed_ssh_source_ip: str,
    enable_direct_https: bool = False,
) -> tuple[str, str]:
    """Ensure the shared per-RG vnet+subnet+NSG exists. Create if missing.

    The vnet is named ``vnet-{prefix}``, subnet ``snet-{prefix}``, and the
    subnet-level NSG ``nsg-{prefix}``. Multiple boards in the same RG share
    this network and ingress ruleset; the first board in the RG sets the
    SSH source IP for everyone (B1 design — re-running a board never
    rewrites the rules of an existing RG's NSG).

    If the vnet exists with a different CIDR than network.bicep declares,
    the subsequent VM deploy will fail loud at ARM ``existing`` resolution
    — by design.

    Args:
        credential: Azure credential (e.g. DefaultAzureCredential).
        subscription_id: Target subscription.
        resource_group: Target resource group (must already exist).
        prefix: Naming prefix (rgName minus any "rg-" prefix).
        location: Azure region for the new vnet (only used on create).
        tags: Tags to apply to the new vnet+subnet+NSG (already merged
            with extraTags by the caller). Ignored when reusing an existing
            network.
        network_bicep_path: Path to ``infra/modules/network.bicep``.
        allowed_ssh_source_ip: Source IP/CIDR for the subnet NSG's SSH
            rule. Only applied on first create of the network; reusing an
            RG silently ignores this value.
        enable_direct_https: Whether to open port 443 at the subnet NSG.
            Only applied on first create.

    Returns:
        ``(vnet_resource_id, subnet_resource_id)``.

    Raises:
        DeploymentError: If a network deploy is needed and fails.
        BoardError: If the vnet exists but the expected subnet does not, or
            if either is in a non-Succeeded provisioning state.
    """
    network_client = NetworkManagementClient(credential, subscription_id)
    vnet_name = f"vnet-{prefix}"
    subnet_name = f"snet-{prefix}"

    try:
        vnet = await asyncio.to_thread(
            network_client.virtual_networks.get,
            resource_group,
            vnet_name,
        )
    except ResourceNotFoundError:
        vnet = None

    if vnet is not None:
        # Existing vnet — verify the expected subnet exists and is healthy.
        state = getattr(vnet, "provisioning_state", None)
        if state and state != "Succeeded":
            msg = (
                f"vnet-{prefix} exists in '{resource_group}' but is in state "
                f"'{state}'. Wait for it to settle, then retry."
            )
            raise BoardError(msg)
        try:
            subnet = await asyncio.to_thread(
                network_client.subnets.get,
                resource_group,
                vnet_name,
                subnet_name,
            )
        except ResourceNotFoundError as exc:
            msg = (
                f"vnet-{prefix} exists in '{resource_group}' but the expected "
                f"subnet '{subnet_name}' is missing. Delete the vnet (or rename "
                f"the resource group) and retry."
            )
            raise BoardError(msg) from exc
        sub_state = getattr(subnet, "provisioning_state", None)
        if sub_state and sub_state != "Succeeded":
            msg = (
                f"subnet '{subnet_name}' in '{resource_group}' is in state "
                f"'{sub_state}'. Wait for it to settle, then retry."
            )
            raise BoardError(msg)
        if not vnet.id or not subnet.id:
            msg = (
                f"vnet-{prefix} or subnet '{subnet_name}' in '{resource_group}' "
                f"returned without a resource ID. Re-run after Azure settles."
            )
            raise BoardError(msg)

        # Older RGs (pre-shared-NSG) have a subnet with no NSG attached.
        # Re-run network.bicep once to attach one; AVM modules are idempotent
        # against the existing vnet/subnet.
        existing_nsg_ref = getattr(subnet, "network_security_group", None)
        if existing_nsg_ref is not None and getattr(existing_nsg_ref, "id", ""):
            return vnet.id, subnet.id

    template = await bicep_build(network_bicep_path)
    outputs = await deploy(
        credential,
        subscription_id,
        resource_group,
        template,
        parameters={
            "prefix": prefix,
            "location": location,
            "tags": tags,
            "allowedSshSourceIP": allowed_ssh_source_ip,
            "enableDirectHttps": enable_direct_https,
        },
        deployment_name=f"network-{prefix}-{int(time.time())}",
    )
    return outputs["vnetResourceId"], outputs["subnetResourceId"]
