"""Bicep compilation and ARM template deployment."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.resource.deployments.aio import DeploymentsMgmtClient
from azure.mgmt.resource.deployments.models import (
    Deployment,
    DeploymentMode,
    DeploymentProperties,
)
from azure.mgmt.resource.resources.models import ResourceGroup

from board.azure.az import az_text
from board.core.errors import DeploymentError

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


async def ensure_resource_group(
    credential: Any,
    subscription_id: str,
    name: str,
    location: str,
    tags: dict[str, str] | None = None,
) -> None:
    """Create a resource group if it doesn't already exist.

    Args:
        credential: Azure credential object.
        subscription_id: Target subscription.
        name: Resource group name.
        location: Azure region (e.g. "australiaeast").
        tags: Optional resource tags.

    Raises:
        DeploymentError: If creation fails or the RG is in a bad state.
    """
    client = ResourceManagementClient(credential, subscription_id)

    try:
        exists = await asyncio.to_thread(client.resource_groups.check_existence, name)
    except Exception as exc:
        msg = f"Failed to check resource group '{name}': {exc}"
        raise DeploymentError(msg) from exc

    if exists:
        # Verify it's in a usable state
        rg = await asyncio.to_thread(client.resource_groups.get, name)
        state = rg.properties.provisioning_state if rg.properties else None
        if state == "Deleting":
            msg = (
                f"Resource group '{name}' is being deleted. "
                "Wait for deletion to complete and retry."
            )
            raise DeploymentError(msg)
        if state and state not in ("Succeeded", "Updating"):
            msg = f"Resource group '{name}' is in state '{state}'. Delete it first."
            raise DeploymentError(msg)
        return

    rg_params = ResourceGroup(
        location=location,
        tags=tags
        or {
            "project": "devvm",
            "managed-by": "board-cli",
        },
    )
    try:
        await asyncio.to_thread(
            lambda: client.resource_groups.create_or_update(name, rg_params),
        )
    except Exception as exc:
        msg = f"Failed to create resource group '{name}': {exc}"
        raise DeploymentError(msg) from exc
