"""board project commands — install-projects, project-status."""

from __future__ import annotations

import asyncio
import os
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

        selected_projects = os.environ.get("BOARD_PROJECTS", "").split() or None
        if selected_projects:
            con.info(f"Projects: {' '.join(selected_projects)}")

        # Pre-flight: if any selected manifest needs Key Vault auth (env or
        # repo-clone) and the user did not pass --keyvault, fail loud now
        # rather than mid-clone with a less obvious error.
        from board.core.manifest import load_all as load_manifests
        from board.core.manifest import required_keyvault_secrets

        manifests = load_manifests(manifest_dir, filter_names=selected_projects)
        env_kv, repo_kv = required_keyvault_secrets(manifests)
        if (env_kv or repo_kv) and not keyvault:
            needs = []
            if repo_kv:
                needs.append(f"clone auth ({', '.join(sorted(repo_kv))})")
            if env_kv:
                needs.append(f"env vars ({', '.join(sorted(env_kv))})")
            con.error("Selected projects require a Key Vault for " + " and ".join(needs) + ".")
            con.info(
                f"Re-run with --keyvault NAME, e.g. board install-projects {name} --keyvault kv-devvm-{name}"
            )
            raise typer.Exit(1)

        from board.provision.orchestrator import provision_projects
        from board.ssh.session import SSHSession

        try:
            async with SSHSession() as ssh:
                await ssh.connect(fqdn, username="devuser", key_path=key_path)
                success_count, fail_count = await provision_projects(
                    ssh=ssh,
                    manifest_dir=manifest_dir,
                    console=con.console,
                    keyvault_name=keyvault,
                    filter_names=selected_projects,
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
                    stdout = (
                        result.stdout.decode()
                        if isinstance(result.stdout, bytes)
                        else result.stdout
                    )
                    for line in stdout.strip().split("\n"):
                        con.console.print(f"  {line}")

                if result.exit_status != 0:
                    con.warn(f"Health check failed (exit {result.exit_status})")
                    con.info("Run: bash ~/projects/.board/check.sh")
        except SSHError as exc:
            con.error(f"SSH connection failed: {exc}")
            raise typer.Exit(1) from exc

    asyncio.run(_run())
