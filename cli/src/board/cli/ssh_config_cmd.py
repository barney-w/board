"""board ssh-config — manage SSH config file entries."""

from __future__ import annotations

from pathlib import Path

import typer

from board.cli import ssh_config_app
from board.core import config as cfg
from board.ssh.config_file import (
    build_ssh_key_config_block,
    remove_managed_block,
    write_managed_block,
)
from board.ui import console as con

DEFAULT_LOCATION = "australiaeast"


@ssh_config_app.command()
def show(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    location: str = typer.Option(DEFAULT_LOCATION, "--location", help="Azure region."),
) -> None:
    """Print the SSH config block for a developer."""
    alias = cfg.ssh_host_alias(name)
    fqdn = cfg.hostname(name, location)
    key_path = str(cfg.ssh_key_path_expanded(name))

    block = build_ssh_key_config_block(alias=alias, hostname=fqdn, key_path=key_path)

    con.console.print("# Add this to ~/.ssh/config\n")
    con.console.print(block)
    con.console.print(f"\n# Usage:  ssh {alias}")
    con.console.print(f"# VS Code: Remote-SSH > {alias}")


@ssh_config_app.command()
def write(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    location: str = typer.Option(DEFAULT_LOCATION, "--location", help="Azure region."),
) -> None:
    """Write SSH config block to ~/.ssh/config (idempotent)."""
    alias = cfg.ssh_host_alias(name)
    fqdn = cfg.hostname(name, location)
    key_path = str(cfg.ssh_key_path_expanded(name))

    block = build_ssh_key_config_block(alias=alias, hostname=fqdn, key_path=key_path)
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
