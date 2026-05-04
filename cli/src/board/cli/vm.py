"""board vm — VM lifecycle subcommands."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any

import typer

from board.azure.vm_tags import resolve_auth_method
from board.cli import vm_app
from board.core import config as cfg
from board.core.errors import BoardError
from board.ui import console as con


def _resolve_rg(rg_arg: str) -> str:
    """Pick up --rg or BOARD_RG. Required — fails loud if neither is set."""
    rg = rg_arg or os.environ.get("BOARD_RG", "")
    if not rg:
        con.error("Resource group is required. Pass --rg or set BOARD_RG.")
        raise typer.Exit(1)
    return rg


def _rg_location(rg: str) -> str:
    """Look up an RG's location via the az CLI. Cached per-process."""
    cache = getattr(_rg_location, "_cache", {})
    if rg in cache:
        return str(cache[rg])
    result = subprocess.run(  # noqa: S603, S607
        ["az", "group", "show", "--name", rg, "--query", "location", "-o", "tsv"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        con.error(f"Could not resolve location for resource group '{rg}'.")
        raise typer.Exit(1)
    location = result.stdout.strip()
    cache[rg] = location
    _rg_location._cache = cache  # type: ignore[attr-defined]
    return location


def _get_power_state(rg: str, vm: str) -> str:
    """Return the VM power state string, e.g. 'running', 'deallocated'. Returns 'unknown' on error."""
    result = subprocess.run(  # noqa: S603, S607
        [
            "az",
            "vm",
            "get-instance-view",
            "--resource-group",
            rg,
            "--name",
            vm,
            "--query",
            "instanceView.statuses[?starts_with(code,'PowerState/')].displayStatus|[0]",
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    raw = result.stdout.strip().lower()
    if "running" in raw:
        return "running"
    if "deallocated" in raw or "stopped" in raw:
        return "stopped"
    return "unknown"


async def _start_vm(rg: str, vm: str) -> None:
    """Start a VM and wait for it to reach running state."""
    from board.azure.auth import get_credential, get_subscription_id
    from board.azure.compute import start_vm

    credential = get_credential()
    sub_id = await get_subscription_id()
    with con.spin(f"Starting {vm}..."):
        await start_vm(credential, sub_id, rg, vm)
    con.success(f"{vm} started")


async def _get_azure_context() -> tuple[Any, str]:
    """Get credential and subscription ID."""
    from board.azure.auth import get_credential, get_subscription_id

    credential = get_credential()
    sub_id = await get_subscription_id()
    return credential, sub_id


@vm_app.command()
def start(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
) -> None:
    """Start a developer VM."""

    async def _start() -> None:
        rg_name = _resolve_rg(rg)
        credential, sub_id = await _get_azure_context()
        vm = cfg.vm_name(rg_name, name)

        from board.azure.compute import start_vm

        with con.spin(f"Starting {vm}..."):
            await start_vm(credential, sub_id, rg_name, vm)
        con.success(f"{vm} started")

    asyncio.run(_start())


@vm_app.command()
def stop(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
) -> None:
    """Stop (deallocate) a developer VM."""

    async def _stop() -> None:
        rg_name = _resolve_rg(rg)
        credential, sub_id = await _get_azure_context()
        vm = cfg.vm_name(rg_name, name)

        from board.azure.compute import deallocate_vm

        with con.spin(f"Deallocating {vm}..."):
            await deallocate_vm(credential, sub_id, rg_name, vm)
        con.success(f"{vm} deallocated")

    asyncio.run(_stop())


@vm_app.command()
def ssh(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
    plain: bool = typer.Option(
        False,
        "--plain",
        help="Skip the 2-column tmux layout, drop into plain bash.",
    ),
) -> None:
    """SSH into a developer VM."""
    rg_name = _resolve_rg(rg)
    location = _rg_location(rg_name)
    vm = cfg.vm_name(rg_name, name)

    # Check VM is running before attempting SSH (avoids silent TCP hang)
    power_state = _get_power_state(rg_name, vm)
    if power_state == "stopped":
        con.warn(f"{vm} is stopped.")
        if not typer.confirm("Start it now?", default=True):
            raise typer.Exit(0)
        asyncio.run(_start_vm(rg_name, vm))

    try:
        auth_method = resolve_auth_method(rg_name, vm)
    except BoardError as exc:
        con.error(str(exc))
        raise typer.Exit(1) from exc

    if auth_method == "entra-id":
        alias = cfg.ssh_host_alias(name)
        fqdn = cfg.hostname(name, location)
        ssh_config_path = Path.home() / ".ssh" / "config"

        # 1. Refresh short-lived Entra ID certificates
        from board.ssh.config_file import (
            SERVICE_PORTS,
            build_entra_id_config_block,
            refresh_entra_certs,
            write_managed_block,
        )

        con.info("Refreshing Entra ID certificates...")
        cert_ok, entra_user = refresh_entra_certs(alias, rg_name, vm)
        if not cert_ok:
            con.error("Failed to refresh Entra ID certificates.")
            con.info("Ensure you are signed in: az login")
            raise typer.Exit(1)

        # 2. Write/update SSH config with User + LocalForward directives
        block = build_entra_id_config_block(
            alias=alias,
            hostname=fqdn,
            user=entra_user or None,
        )
        write_managed_block(ssh_config_path, alias, block)

        # 3. Connect via the SSH alias (picks up LocalForward from config)
        con.info(f"Connecting to {vm}...")
        con.info("Port forwards (active once connected):")
        for _local_port, _remote_port, label, url in SERVICE_PORTS:
            con.info(f"  {label:15s} {url}")
        con.info("")
        con.info("Type 'exit' or press Ctrl+D to disconnect.")
        con.info("Run 'vibe' on the VM for the 2-column tmux workspace.")
        con.info("")
        ssh_argv = ["ssh", alias]
        if plain:
            ssh_argv += ["-t", "BOARD_NO_TMUX=1 exec bash -l"]
        subprocess.run(ssh_argv, check=False)  # noqa: S603, S607
    else:
        fqdn = cfg.hostname(name, location)
        key_path = cfg.ssh_key_path_expanded(name)

        if not key_path.exists():
            con.error(f"SSH key not found: {key_path}")
            con.info(f"Generate one with: board vm keygen {name}")
            raise typer.Exit(1)

        con.info(f"Connecting to {fqdn}...")
        ssh_argv = ["ssh", "-i", str(key_path), f"devuser@{fqdn}"]
        if plain:
            ssh_argv += ["-t", "BOARD_NO_TMUX=1 exec bash -l"]
        subprocess.run(ssh_argv, check=False)  # noqa: S603, S607


@vm_app.command()
def ls(
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
) -> None:
    """List all VMs in the resource group."""

    async def _ls() -> None:
        rg_name = _resolve_rg(rg)
        credential, sub_id = await _get_azure_context()

        from board.azure.compute import list_vms

        with con.spin("Loading VMs..."):
            vms = await list_vms(credential, sub_id, rg_name)

        if not vms:
            con.info(f"No VMs found in {rg_name}")
            return

        from rich.table import Table

        table = Table(title=f"VMs in {rg_name}")
        table.add_column("Name", style="bold")
        table.add_column("Size")
        table.add_column("State")
        table.add_column("Location")

        for vm in vms:
            state = vm["power_state"]
            state_style = (
                "green" if state == "running" else "dim" if "deallocat" in state else "yellow"
            )
            table.add_row(
                vm["name"],
                vm["vm_size"] or "?",
                f"[{state_style}]{state}[/{state_style}]",
                vm["location"] or "?",
            )

        con.console.print(table)

    asyncio.run(_ls())


@vm_app.command()
def status(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
) -> None:
    """Show detailed status for a specific VM."""

    async def _status() -> None:
        rg_name = _resolve_rg(rg)
        location = _rg_location(rg_name)
        credential, sub_id = await _get_azure_context()
        vm = cfg.vm_name(rg_name, name)

        from board.azure.compute import get_vm_status

        with con.spin(f"Checking {vm}..."):
            info = await get_vm_status(credential, sub_id, rg_name, vm)

        fqdn = cfg.hostname(name, location)
        key_path = cfg.ssh_key_path_expanded(name)

        con.summary_box(
            f"VM: {info['name']}",
            [
                f"Power state:        {info['power_state']}",
                f"Provisioning state: {info['provisioning_state']}",
                f"VM size:            {info['vm_size']}",
                f"Location:           {info['location']}",
                f"FQDN:               {fqdn}",
                f"SSH key:            {key_path}",
                "",
                f"SSH:   ssh devvm-{name}",
            ],
        )

    asyncio.run(_status())


@vm_app.command()
def delete(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a developer VM."""

    async def _delete() -> None:
        rg_name = _resolve_rg(rg)
        credential, sub_id = await _get_azure_context()
        vm = cfg.vm_name(rg_name, name)

        if not yes:
            con.warn(f"This will permanently delete VM {vm}.")
            if con.console.input("[bold]Type the VM name to confirm: [/bold]") != vm:
                con.info("Cancelled.")
                return

        from board.azure.compute import delete_vm

        with con.spin(f"Deleting {vm}..."):
            await delete_vm(credential, sub_id, rg_name, vm)
        con.success(f"{vm} deleted")

        # Clean up SSH config
        from board.ssh.config_file import remove_managed_block

        ssh_config_path = Path.home() / ".ssh" / "config"
        alias = cfg.ssh_host_alias(name)
        if remove_managed_block(ssh_config_path, alias):
            con.success(f"Removed SSH config entry for {alias}")

    asyncio.run(_delete())


@vm_app.command()
def keygen(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
) -> None:
    """Generate an SSH keypair for a developer VM."""

    async def _keygen() -> None:
        key_path = cfg.ssh_key_path_expanded(name)

        if key_path.exists():
            con.warn(f"Key already exists: {key_path}")
            from board.ui.prompts import confirm

            if not confirm("Overwrite?", default=False):
                con.info("Cancelled.")
                return

        from board.ssh.keys import generate_keypair

        _, pub_key = await generate_keypair(key_path)
        con.success(f"Private key: {key_path}")
        con.success(f"Public key:  {key_path}.pub")
        con.info(f"Public key contents:\n  {pub_key}")

    asyncio.run(_keygen())


# ── RBAC role definitions ──
# Maps board roles to Azure RBAC roles and their scopes.

BOARD_ROLES: dict[str, list[dict[str, str]]] = {
    "admin": [
        {"role": "Contributor", "scope": "rg"},
        {"role": "Key Vault Administrator", "scope": "rg"},
        {"role": "Virtual Machine Administrator Login", "scope": "rg"},
    ],
    "developer": [
        {"role": "Reader", "scope": "rg"},
        {"role": "Virtual Machine User Login", "scope": "rg"},
    ],
    "viewer": [
        {"role": "Reader", "scope": "rg"},
    ],
}


def _resolve_principal_id(email: str) -> str:
    """Resolve Entra ID principal (object) ID from email."""
    result = subprocess.run(  # noqa: S603, S607
        ["az", "ad", "user", "show", "--id", email, "--query", "id", "-o", "tsv"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        con.error(f"Could not find Entra ID user: {email}")
        raise typer.Exit(1)
    return result.stdout.strip()


def _resolve_vm_resource_id(rg: str, vm_name_str: str) -> str:
    """Get the full resource ID of a VM."""
    result = subprocess.run(  # noqa: S603, S607
        [
            "az",
            "vm",
            "show",
            "--resource-group",
            rg,
            "--name",
            vm_name_str,
            "--query",
            "id",
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        con.error(f"Could not find VM: {vm_name_str} in {rg}")
        raise typer.Exit(1)
    return result.stdout.strip()


def _resolve_rg_resource_id(rg: str) -> str:
    """Get the full resource ID of a resource group."""
    result = subprocess.run(  # noqa: S603, S607
        ["az", "group", "show", "--name", rg, "--query", "id", "-o", "tsv"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        con.error(f"Could not find resource group: {rg}")
        raise typer.Exit(1)
    return result.stdout.strip()


def _assign_role(principal_id: str, role_name: str, scope: str) -> bool:
    """Assign an Azure RBAC role. Returns True on success."""
    result = subprocess.run(  # noqa: S603, S607
        [
            "az",
            "role",
            "assignment",
            "create",
            "--assignee-object-id",
            principal_id,
            "--assignee-principal-type",
            "User",
            "--role",
            role_name,
            "--scope",
            scope,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Ignore "already exists" errors
        if "already exists" in result.stderr.lower() or "conflict" in result.stderr.lower():
            return True
        con.error(f"Failed to assign {role_name}: {result.stderr.strip()}")
        return False
    return True


@vm_app.command(name="grant-access")
def grant_access(
    email: str = typer.Argument(..., help="Developer's email address."),
    name: str = typer.Argument(..., help="Developer name / VM name suffix (e.g. jbloggs)."),
    role: str = typer.Option(
        "developer", "--role", "-r", help="Board role: admin, developer, viewer."
    ),
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
) -> None:
    """Grant access to a developer VM with a board role (admin/developer/viewer)."""
    if role not in BOARD_ROLES:
        con.error(f"Unknown role: {role}. Must be one of: {', '.join(BOARD_ROLES)}")
        raise typer.Exit(1)

    rg_name = _resolve_rg(rg)
    vm_name_str = cfg.vm_name(rg_name, name)

    principal_id = _resolve_principal_id(email)

    # Resolve scopes we'll need
    rg_id: str | None = None
    vm_id: str | None = None
    role_defs = BOARD_ROLES[role]

    needs_rg = any(r["scope"] == "rg" for r in role_defs)
    needs_vm = any(r["scope"] == "vm" for r in role_defs)

    if needs_rg:
        rg_id = _resolve_rg_resource_id(rg_name)
    if needs_vm:
        vm_id = _resolve_vm_resource_id(rg_name, vm_name_str)

    con.info(f"Granting '{role}' role to {email}...")
    failures = 0
    for role_def in role_defs:
        scope = rg_id if role_def["scope"] == "rg" else vm_id
        assert scope is not None
        if _assign_role(principal_id, role_def["role"], scope):
            con.success(f"  {role_def['role']} @ {role_def['scope']}")
        else:
            failures += 1

    if failures:
        con.error(f"{failures} role assignment(s) failed")
        raise typer.Exit(1)

    con.success(f"Done. {email} now has '{role}' access.")
    if role != "viewer":
        con.info(f"SSH: az ssh vm --resource-group {rg_name} --name {vm_name_str}")
