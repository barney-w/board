"""board project commands — install-projects, project-status."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from board.core import config as cfg
from board.core.errors import BoardError, SSHError
from board.ui import console as con

DEFAULT_LOCATION = "australiaeast"


def _find_manifest_dir() -> Path:
    """Locate the projects/ manifest directory."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "projects"
        if candidate.is_dir() and list(candidate.glob("*.project.yaml")):
            return candidate
    return cwd / "projects"


def install_projects_command(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    keyvault: str = typer.Option("", "--keyvault", help="Key Vault name for secrets."),
    location: str = typer.Option(DEFAULT_LOCATION, "--location", help="Azure region."),
) -> None:
    """Install projects on a board from manifest files."""

    async def _run() -> None:
        fqdn = cfg.hostname(name, location)
        key_path = cfg.ssh_key_path_expanded(name)

        if not key_path.exists():
            con.error(f"SSH key not found: {key_path}")
            con.info(f"Generate one with: board vm keygen {name}")
            raise typer.Exit(1)

        manifest_dir = _find_manifest_dir()
        if not manifest_dir.is_dir():
            con.error(f"No manifest directory found at {manifest_dir}")
            raise typer.Exit(1)

        from board.provision.orchestrator import provision_projects
        from board.ssh.session import SSHSession

        try:
            async with SSHSession() as ssh:
                await ssh.connect(fqdn, username="devuser", key_path=key_path)
                success_count, fail_count = await provision_projects(
                    ssh=ssh,
                    manifest_dir=manifest_dir,
                    console=con,
                    keyvault_name=keyvault,
                )
            if fail_count > 0:
                con.warn(f"{fail_count} project(s) had issues")
                raise typer.Exit(1)
        except SSHError as exc:
            con.error(f"SSH connection failed: {exc}")
            raise typer.Exit(1) from exc
        except BoardError as exc:
            con.error(f"Provisioning failed: {exc}")
            raise typer.Exit(1) from exc

    asyncio.run(_run())


def project_status_command(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    location: str = typer.Option(DEFAULT_LOCATION, "--location", help="Azure region."),
) -> None:
    """Check project service health on a board."""

    async def _run() -> None:
        fqdn = cfg.hostname(name, location)
        key_path = cfg.ssh_key_path_expanded(name)

        if not key_path.exists():
            con.error(f"SSH key not found: {key_path}")
            raise typer.Exit(1)

        from board.ssh.session import SSHSession

        try:
            async with SSHSession() as ssh:
                await ssh.connect(fqdn, username="devuser", key_path=key_path)

                # Check if check script exists
                check = await ssh.run("test -x ~/projects/.board/check.sh", check=False)
                if check.exit_status != 0:
                    con.info("No check script found. Run install-projects first.")
                    return

                result = await ssh.run("bash ~/projects/.board/check.sh", check=False)
                if result.stdout:
                    for line in result.stdout.strip().split("\n"):
                        con.console.print(f"  {line}")

                if result.exit_status != 0:
                    con.warn(f"Health check failed (exit {result.exit_status})")
                    con.info("Run: bash ~/projects/.board/check.sh")
        except SSHError as exc:
            con.error(f"SSH connection failed: {exc}")
            raise typer.Exit(1) from exc

    asyncio.run(_run())
