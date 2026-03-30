"""board export-pass — create an encrypted board pass for another developer."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from board.core import config as cfg
from board.ui import console as con
from board.ui import prompts

DEFAULT_LOCATION = "australiaeast"
DEFAULT_REGION = "aue"


def _find_vsix() -> Path | None:
    """Locate the extension .vsix in the extension/ directory."""
    ext_dir = Path(__file__).resolve().parents[4] / "extension"
    if not ext_dir.is_dir():
        return None
    candidates = sorted(ext_dir.glob("*.vsix"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


async def _run_export_pass(
    name: str = "",
    environment: str = "",
    region: str = "",
    region_short: str = "",
) -> None:
    """Create an encrypted board pass."""
    # Resolve parameters
    if not name:
        name = await prompts.input_validated(
            "Developer name",
            pattern=r"^[a-z][a-z0-9]{0,11}$",
            message="Must be lowercase, start with a letter, max 12 chars",
        )

    if not environment:
        environment = await prompts.input_text("Environment", default="personal")
    region = region or DEFAULT_LOCATION
    region_short = region_short or DEFAULT_REGION

    # Derive names
    fqdn = cfg.hostname(name, region)
    rg = cfg.resource_group(environment, region_short)
    vm = cfg.vm_name(environment, region_short, name)
    key_path = cfg.ssh_key_path_expanded(name)

    # Read SSH keys
    if not key_path.exists():
        con.error(f"SSH private key not found: {key_path}")
        con.info(f"Generate one with: board vm keygen {name}")
        return

    pub_path = key_path.with_suffix(".pub")
    if not pub_path.exists():
        con.error(f"SSH public key not found: {pub_path}")
        return

    private_key = key_path.read_text()
    public_key = pub_path.read_text().strip()

    # Get passphrase
    passphrase = await prompts.secret("Passphrase for board pass (min 8 chars)")
    if len(passphrase) < 8:
        con.error("Passphrase must be at least 8 characters.")
        return

    passphrase_confirm = await prompts.secret("Confirm passphrase")
    if passphrase != passphrase_confirm:
        con.error("Passphrases do not match.")
        return

    # Build payload
    from board.bundle.payload import build_payload

    payload = build_payload(
        developer_name=name,
        environment=environment,
        region=region,
        region_short=region_short,
        hostname=fqdn,
        username="devuser",
        auth_method="ssh-key",
        ssh_private_key=private_key,
        ssh_public_key=public_key,
        resource_group=rg,
        vm_name=vm,
    )

    # Check for tunnel URL
    tunnel_url_path = key_path.parent / f".board-tunnel-{name}"
    if tunnel_url_path.exists():
        # If we stored the tunnel URL, we could add it to browserIde
        pass

    # Encrypt
    from board.bundle.crypto import encrypt

    payload_json = payload.model_dump_json(by_alias=True)
    envelope = encrypt(payload_json, passphrase)

    # Write .board-pass file
    output_dir = Path.cwd()
    pass_filename = f"{name}.board-pass"
    pass_path = output_dir / pass_filename

    pass_path.write_text(envelope.model_dump_json(indent=2))

    # Build starter-kit zip
    from board.bundle.package import build_zip
    from board.bundle.svg import render_board_pass_png

    templates_dir = Path(__file__).resolve().parents[1] / "bundle" / "templates"
    vsix_path = _find_vsix()

    if vsix_path:
        board_pass_png = render_board_pass_png(
            developer_name=name,
            environment=environment,
            region=region,
            region_short=region_short,
            vm_name=vm,
            auth_method="ssh-key",
            issued_at=payload.issued_at or "",
            valid_until=payload.valid_until or "",
        )
        zip_path = build_zip(
            board_pass_path=pass_path,
            vsix_path=vsix_path,
            output_dir=output_dir,
            name=name,
            templates_dir=templates_dir,
            board_pass_png=board_pass_png,
        )
        pass_path.unlink()
        bundle_filename = zip_path.name
        con.success(f"Board pass written: {zip_path}")
    else:
        con.warn("No .vsix found — shipping board pass without starter kit.")
        con.info("Build the extension first: cd extension && npm run package")
        bundle_filename = pass_filename

    # Display boarding pass
    from board.ui.boarding_pass import render_boarding_pass

    render_boarding_pass(
        name=name,
        environment=environment,
        region=region,
        region_short=region_short,
        hostname=fqdn,
        auth_method="ssh-key",
        filename=bundle_filename,
        issued_at=payload.issued_at or "",
        valid_until=payload.valid_until or "",
    )

    con.info(f"Send {bundle_filename} to {name}.")
    con.info("Share the passphrase separately (different channel).")
    if vsix_path:
        con.info("They unzip it, double-click 'Setup Board', enter the passphrase — done.")


def export_pass_command(
    name: str = typer.Argument("", help="Developer name (e.g. jbloggs)."),
    environment: str = typer.Option("", "--env", help="Environment name."),
    region: str = typer.Option("", "--region", help="Azure region."),
    region_short: str = typer.Option("", "--region-short", help="Short region code."),
) -> None:
    """Create an encrypted board pass for a developer."""
    asyncio.run(_run_export_pass(name, environment, region, region_short))
