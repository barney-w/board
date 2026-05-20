"""VM operations via Azure Compute Management SDK."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import RunCommandInput
from azure.mgmt.network import NetworkManagementClient

from board.core.errors import BoardError

log = logging.getLogger(__name__)


async def list_vms(
    credential: Any,
    subscription_id: str,
    resource_group: str,
) -> list[dict[str, Any]]:
    """List VMs in a resource group with their power state.

    Returns:
        List of dicts with keys: name, vm_size, os, power_state, location.
    """
    client = ComputeManagementClient(credential, subscription_id)
    vms_raw = await asyncio.to_thread(
        lambda: list(client.virtual_machines.list(resource_group)),
    )
    results = []
    for vm in vms_raw:
        vm_name = vm.name or ""
        # Fetch instance view for power state
        instance_view = await asyncio.to_thread(
            client.virtual_machines.instance_view,
            resource_group,
            vm_name,
        )
        power_state = "unknown"
        if instance_view.statuses:
            for status in instance_view.statuses:
                if status.code and status.code.startswith("PowerState/"):
                    power_state = status.code.split("/", 1)[1]
                    break
        results.append(
            {
                "name": vm_name,
                "vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else None,
                "os": (
                    vm.storage_profile.os_disk.os_type
                    if vm.storage_profile and vm.storage_profile.os_disk
                    else None
                ),
                "power_state": power_state,
                "location": vm.location,
                "tags": dict(vm.tags) if vm.tags else {},
            }
        )
    return results


async def get_vm_status(
    credential: Any,
    subscription_id: str,
    resource_group: str,
    vm_name: str,
) -> dict[str, Any]:
    """Get detailed VM status including power state and provisioning state.

    Returns:
        Dict with keys: name, power_state, provisioning_state, vm_size, location.
    """
    client = ComputeManagementClient(credential, subscription_id)
    vm = await asyncio.to_thread(
        client.virtual_machines.get,
        resource_group,
        vm_name,
        expand="instanceView",
    )
    power_state = "unknown"
    provisioning_state = "unknown"
    if vm.instance_view and vm.instance_view.statuses:
        for status in vm.instance_view.statuses:
            if not status.code:
                continue
            if status.code.startswith("PowerState/"):
                power_state = status.code.split("/", 1)[1]
            elif status.code.startswith("ProvisioningState/"):
                provisioning_state = status.code.split("/", 1)[1]
    return {
        "name": vm.name,
        "power_state": power_state,
        "provisioning_state": provisioning_state,
        "vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else None,
        "location": vm.location,
    }


async def start_vm(
    credential: Any,
    subscription_id: str,
    resource_group: str,
    vm_name: str,
) -> None:
    """Start a VM (no-op if already running)."""
    client = ComputeManagementClient(credential, subscription_id)
    poller = await asyncio.to_thread(
        client.virtual_machines.begin_start,
        resource_group,
        vm_name,
    )
    await asyncio.to_thread(poller.result)


async def stop_vm(
    credential: Any,
    subscription_id: str,
    resource_group: str,
    vm_name: str,
) -> None:
    """Stop (power off) a VM without deallocating. VM still incurs charges."""
    client = ComputeManagementClient(credential, subscription_id)
    poller = await asyncio.to_thread(
        client.virtual_machines.begin_power_off,
        resource_group,
        vm_name,
    )
    await asyncio.to_thread(poller.result)


async def deallocate_vm(
    credential: Any,
    subscription_id: str,
    resource_group: str,
    vm_name: str,
) -> None:
    """Deallocate a VM (stop + release compute resources)."""
    client = ComputeManagementClient(credential, subscription_id)
    poller = await asyncio.to_thread(
        client.virtual_machines.begin_deallocate,
        resource_group,
        vm_name,
    )
    await asyncio.to_thread(poller.result)


async def delete_vm(
    credential: Any,
    subscription_id: str,
    resource_group: str,
    vm_name: str,
) -> None:
    """Delete a VM and its associated public IP addresses.

    The NIC is auto-deleted by Azure (deleteOption: Delete in the Bicep
    template), but PIPs are standalone resources that must be cleaned up
    explicitly.
    """
    compute = ComputeManagementClient(credential, subscription_id)
    network = NetworkManagementClient(credential, subscription_id)

    # Discover public IPs attached via NICs before deleting the VM
    pip_ids: list[str] = []
    vm = await asyncio.to_thread(
        compute.virtual_machines.get,
        resource_group,
        vm_name,
    )
    if vm.network_profile and vm.network_profile.network_interfaces:
        for nic_ref in vm.network_profile.network_interfaces:
            if not nic_ref.id:
                continue
            nic_name = nic_ref.id.rsplit("/", 1)[-1]
            try:
                nic = await asyncio.to_thread(
                    network.network_interfaces.get,
                    resource_group,
                    nic_name,
                )
            except Exception:
                log.warning("Could not read NIC %s, skipping PIP cleanup", nic_name)
                continue
            for ip_cfg in nic.ip_configurations or []:
                if ip_cfg.public_ip_address and ip_cfg.public_ip_address.id:
                    pip_ids.append(ip_cfg.public_ip_address.id)

    # Delete the VM (NIC auto-deletes via deleteOption)
    poller = await asyncio.to_thread(
        compute.virtual_machines.begin_delete,
        resource_group,
        vm_name,
    )
    await asyncio.to_thread(poller.result)

    # Clean up orphaned PIPs
    for pip_id in pip_ids:
        pip_name = pip_id.rsplit("/", 1)[-1]
        log.info("Deleting orphaned public IP: %s", pip_name)
        try:
            pip_poller = await asyncio.to_thread(
                network.public_ip_addresses.begin_delete,
                resource_group,
                pip_name,
            )
            await asyncio.to_thread(pip_poller.result)
        except Exception:
            log.warning("Failed to delete public IP %s (may already be removed)", pip_name)


async def list_skus(
    credential: Any,
    subscription_id: str,
    location: str,
    filter_pattern: str = "",
) -> list[dict[str, Any]]:
    """List available VM SKUs for a location using the REST API.

    Uses the Compute Resource SKUs API directly rather than ``az vm list-skus``
    which takes 73+ seconds in some regions.

    Args:
        credential: Azure credential.
        subscription_id: Target subscription.
        location: Azure region (e.g. "australiaeast").
        filter_pattern: Optional substring filter on SKU name.

    Returns:
        List of dicts with keys: name, family, vcpus, memory_gb.
    """
    client = ComputeManagementClient(credential, subscription_id)
    all_skus = await asyncio.to_thread(
        lambda: list(client.resource_skus.list(filter=f"location eq '{location}'")),
    )
    results = []
    for sku in all_skus:
        if sku.resource_type != "virtualMachines":
            continue
        if filter_pattern and filter_pattern.lower() not in (sku.name or "").lower():
            continue
        # Check for restrictions (e.g. not available in this subscription)
        if sku.restrictions:
            restricted = False
            for r in sku.restrictions:
                if r.type == "Location" and r.reason_code == "NotAvailableForSubscription":
                    restricted = True
                    break
            if restricted:
                continue
        # Extract capabilities
        vcpus = 0
        memory_gb = 0.0
        family = sku.family or ""
        if sku.capabilities:
            for cap in sku.capabilities:
                if cap.name == "vCPUs":
                    vcpus = int(cap.value or 0)
                elif cap.name == "MemoryGB":
                    memory_gb = float(cap.value or 0)
        results.append(
            {
                "name": sku.name,
                "family": family,
                "vcpus": vcpus,
                "memory_gb": memory_gb,
            }
        )
    return results


async def run_command(
    credential: Any,
    subscription_id: str,
    resource_group: str,
    vm_name: str,
    script: str,
) -> str:
    """Run a shell command on a VM via the Azure Run Command API.

    Args:
        credential: Azure credential.
        subscription_id: Target subscription.
        resource_group: Resource group containing the VM.
        vm_name: VM name.
        script: Shell script to execute.

    Returns:
        Combined stdout output from the command.

    Raises:
        BoardError: If the command execution fails.
    """
    client = ComputeManagementClient(credential, subscription_id)
    run_params = RunCommandInput(
        command_id="RunShellScript",
        script=[script],
    )
    try:
        poller = await asyncio.to_thread(
            lambda: client.virtual_machines.begin_run_command(
                resource_group,
                vm_name,
                run_params,
            ),
        )
        result = await asyncio.to_thread(poller.result)
    except Exception as exc:
        msg = f"Run command failed on {vm_name}: {exc}"
        raise BoardError(msg) from exc

    output_lines = []
    if result.value:
        for msg_obj in result.value:
            if msg_obj.message:
                output_lines.append(msg_obj.message)
    return "\n".join(output_lines)
