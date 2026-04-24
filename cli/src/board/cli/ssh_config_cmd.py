"""board ssh-config — manage SSH config file entries."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer

from board.cli import ssh_config_app
from board.core import config as cfg
from board.ssh.config_file import (
    build_entra_id_config_block,
    build_ssh_key_config_block,
    remove_managed_block,
    write_managed_block,
)
from board.ui import console as con

DEFAULT_LOCATION = "australiaeast"
DEFAULT_REGION = "aue"


def _resolve_env() -> str:
    return os.environ.get("BOARD_ENVIRONMENT", "personal")


def _resolve_auth_method(rg: str, vm: str) -> str:
    """Read the ``auth-method`` tag from the VM. Falls back to ``ssh-key``."""
    result = subprocess.run(  # noqa: S603, S607
        [
            "az", "vm", "show",
            "--resource-group", rg,
            "--name", vm,
            "--query", 'tags."auth-method"',
            "-o", "tsv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    tag = result.stdout.strip()
    return tag if tag in ("entra-id", "ssh-key") else "ssh-key"


def _build_block(
    name: str,
    location: str,
    auth: str,
    env: str,
    region_short: str,
) -> str:
    """Build the appropriate SSH config block based on auth method."""
    alias = cfg.ssh_host_alias(name)
    fqdn = cfg.hostname(name, location)

    if auth == "auto":
        rg = cfg.resource_group(env, region_short)
        vm = cfg.vm_name(env, region_short, name)
        auth = _resolve_auth_method(rg, vm)
        con.info(f"Auth method: {auth} (from VM tag)")

    if auth == "entra-id":
        return build_entra_id_config_block(alias=alias, hostname=fqdn)

    key_path = str(cfg.ssh_key_path_expanded(name))
    return build_ssh_key_config_block(alias=alias, hostname=fqdn, key_path=key_path)


@ssh_config_app.command()
def show(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    location: str = typer.Option(DEFAULT_LOCATION, "--location", help="Azure region."),
    auth: str = typer.Option("auto", "--auth", help="Auth method: auto, ssh-key, or entra-id."),
    env: str = typer.Option("", "--env", help="Environment (default: $BOARD_ENVIRONMENT or personal)."),
    region_short: str = typer.Option(DEFAULT_REGION, "--region-short", help="Short region code."),
) -> None:
    """Print the SSH config block for a developer."""
    resolved_env = env or _resolve_env()
    alias = cfg.ssh_host_alias(name)
    block = _build_block(name, location, auth, resolved_env, region_short)

    con.console.print("# Add this to ~/.ssh/config\n")
    con.console.print(block)
    con.console.print(f"\n# Usage:  ssh {alias}")
    con.console.print(f"# VS Code: Remote-SSH > {alias}")


@ssh_config_app.command()
def write(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    location: str = typer.Option(DEFAULT_LOCATION, "--location", help="Azure region."),
    auth: str = typer.Option("auto", "--auth", help="Auth method: auto, ssh-key, or entra-id."),
    env: str = typer.Option("", "--env", help="Environment (default: $BOARD_ENVIRONMENT or personal)."),
    region_short: str = typer.Option(DEFAULT_REGION, "--region-short", help="Short region code."),
) -> None:
    """Write SSH config block to ~/.ssh/config (idempotent)."""
    resolved_env = env or _resolve_env()
    alias = cfg.ssh_host_alias(name)
    block = _build_block(name, location, auth, resolved_env, region_short)
    config_path = Path.home() / ".ssh" / "config"

    write_managed_block(config_path, alias, block)
    con.success(f"SSH config written to {config_path} (Host {alias})")


@ssh_config_app.command()
def remove(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
) -> None:
    """Remove SSH config block from ~/.ssh/config."""
    alias = cfg.ssh_host_alias(name)
    config_path = Path.home() / ".ssh" / "config"

    if remove_managed_block(config_path, alias):
        con.success(f"SSH config block removed for {alias}")
    else:
        con.info(f"No SSH config block found for {alias}")
