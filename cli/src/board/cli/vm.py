"""board vm — VM lifecycle subcommands."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import typer

from board.cli import vm_app
from board.core import config as cfg
from board.ui import console as con

DEFAULT_LOCATION = "australiaeast"
DEFAULT_REGION = "aue"


def _resolve_env() -> str:
    return os.environ.get("BOARD_ENVIRONMENT", "personal")


def _resolve_rg(env: str | None = None) -> str:
    return cfg.resource_group(env or _resolve_env(), DEFAULT_REGION)


async def _get_azure_context() -> tuple:
    """Get credential and subscription ID."""
    from board.azure.auth import get_credential, get_subscription_id

    credential = get_credential()
    sub_id = await get_subscription_id()
    return credential, sub_id


@vm_app.command()
def start(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    env: str = typer.Option("", "--env", help="Environment name."),
) -> None:
    """Start a developer VM."""

    async def _start() -> None:
        credential, sub_id = await _get_azure_context()
        rg = _resolve_rg(env or None)
        vm = cfg.vm_name(env or _resolve_env(), DEFAULT_REGION, name)

        from board.azure.compute import start_vm

        with con.spin(f"Starting {vm}..."):
            await start_vm(credential, sub_id, rg, vm)
        con.success(f"{vm} started")

    asyncio.run(_start())


@vm_app.command()
def stop(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    env: str = typer.Option("", "--env", help="Environment name."),
) -> None:
    """Stop (deallocate) a developer VM."""

    async def _stop() -> None:
        credential, sub_id = await _get_azure_context()
        rg = _resolve_rg(env or None)
        vm = cfg.vm_name(env or _resolve_env(), DEFAULT_REGION, name)

        from board.azure.compute import deallocate_vm

        with con.spin(f"Deallocating {vm}..."):
            await deallocate_vm(credential, sub_id, rg, vm)
        con.success(f"{vm} deallocated")

    asyncio.run(_stop())


@vm_app.command()
def ssh(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
) -> None:
    """SSH into a developer VM."""
    fqdn = cfg.hostname(name, DEFAULT_LOCATION)
    key_path = cfg.ssh_key_path_expanded(name)

    if not key_path.exists():
        con.error(f"SSH key not found: {key_path}")
        con.info(f"Generate one with: board vm keygen {name}")
        raise typer.Exit(1)

    con.info(f"Connecting to {fqdn}...")
    subprocess.run(  # noqa: S603, S607
        ["ssh", "-i", str(key_path), f"devuser@{fqdn}"],
        check=False,
    )


@vm_app.command()
def ls(
    env: str = typer.Option("", "--env", help="Environment name."),
) -> None:
    """List all VMs in the environment."""

    async def _ls() -> None:
        credential, sub_id = await _get_azure_context()
        rg = _resolve_rg(env or None)

        from board.azure.compute import list_vms

        with con.spin("Loading VMs..."):
            vms = await list_vms(credential, sub_id, rg)

        if not vms:
            con.info(f"No VMs found in {rg}")
            return

        from rich.table import Table

        table = Table(title=f"VMs in {rg}")
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
    env: str = typer.Option("", "--env", help="Environment name."),
) -> None:
    """Show detailed status for a specific VM."""

    async def _status() -> None:
        credential, sub_id = await _get_azure_context()
        rg = _resolve_rg(env or None)
        vm = cfg.vm_name(env or _resolve_env(), DEFAULT_REGION, name)

        from board.azure.compute import get_vm_status

        with con.spin(f"Checking {vm}..."):
            info = await get_vm_status(credential, sub_id, rg, vm)

        fqdn = cfg.hostname(name, DEFAULT_LOCATION)
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
    env: str = typer.Option("", "--env", help="Environment name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a developer VM."""

    async def _delete() -> None:
        credential, sub_id = await _get_azure_context()
        rg = _resolve_rg(env or None)
        vm = cfg.vm_name(env or _resolve_env(), DEFAULT_REGION, name)

        if not yes:
            con.warn(f"This will permanently delete VM {vm}.")
            if con.console.input("[bold]Type the VM name to confirm: [/bold]") != vm:
                con.info("Cancelled.")
                return

        from board.azure.compute import delete_vm

        with con.spin(f"Deleting {vm}..."):
            await delete_vm(credential, sub_id, rg, vm)
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
