"""board utility commands — wait-ready, rotate-key."""

from __future__ import annotations

import asyncio
import subprocess

import typer

from board.core import config as cfg
from board.core.errors import SSHError
from board.ui import console as con

DEFAULT_LOCATION = "australiaeast"


def wait_ready_command(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    location: str = typer.Option(DEFAULT_LOCATION, "--location", help="Azure region."),
    timeout: int = typer.Option(600, "--timeout", help="Max wait in seconds."),
) -> None:
    """Wait for cloud-init to complete on a board."""

    async def _run() -> None:
        fqdn = cfg.hostname(name, location)
        key_path = cfg.ssh_key_path_expanded(name)

        from board.provision.cloud_init import wait_for_cloud_init

        try:
            await wait_for_cloud_init(
                hostname=fqdn,
                key_path=str(key_path),
                user="devuser",
                max_wait=timeout,
                console=con.console,
            )
        except SSHError as exc:
            con.error(str(exc))
            raise typer.Exit(1) from exc

    asyncio.run(_run())


def rotate_key_command(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    location: str = typer.Option(DEFAULT_LOCATION, "--location", help="Azure region."),
) -> None:
    """Rotate SSH key for a board (invalidates existing board passes)."""
    old_key = cfg.ssh_key_path_expanded(name)
    if not old_key.exists():
        con.error(f"No existing key at {old_key}. Use 'board vm keygen {name}' instead.")
        raise typer.Exit(1)

    fqdn = cfg.hostname(name, location)
    new_key = old_key.with_suffix(".new")
    new_pub = old_key.with_suffix(".new.pub")

    con.info(f"Rotating SSH key for {name}...")

    # Generate new key to temp location
    subprocess.run(  # noqa: S603, S607
        ["ssh-keygen", "-t", "ed25519", "-C", f"devvm-{name}", "-f", str(new_key), "-N", ""],
        check=True,
    )
    new_pub_content = new_pub.read_text().strip()

    # Push new public key to VM using old key
    con.info("Updating authorized_keys on VM...")
    result = subprocess.run(  # noqa: S603, S607
        [
            "ssh",
            "-i",
            str(old_key),
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"devuser@{fqdn}",
            f'echo "{new_pub_content}" > ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys',
        ],
        check=False,
    )
    if result.returncode != 0:
        con.error("Failed to update authorized_keys on VM.")
        new_key.unlink(missing_ok=True)
        new_pub.unlink(missing_ok=True)
        raise typer.Exit(1)

    # Replace old key with new key
    new_key.rename(old_key)
    new_pub.rename(old_key.with_suffix(".pub"))

    con.success(f"Key rotated for {name}. Old board passes are now invalid.")
    con.info(f"Run 'board export-pass {name}' to create a new board pass.")
