"""board export-pass — create a board pass for another developer.

Entra ID passes are plaintext (no passphrase needed).
SSH-key passes are encrypted with AES-256-GCM.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import typer

from board.core import config as cfg
from board.ui import console as con
from board.ui import prompts

DEFAULT_LOCATION = "australiaeast"
DEFAULT_REGION = "aue"


def _resolve_auth_method(rg: str, vm: str) -> str:
    """Read the ``auth-method`` tag from the VM. Falls back to ``ssh-key``."""
    result = subprocess.run(  # noqa: S603, S607
        [
            "az",
            "vm",
            "show",
            "--resource-group",
            rg,
            "--name",
            vm,
            "--query",
            'tags."auth-method"',
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    tag = result.stdout.strip()
    return tag if tag in ("entra-id", "ssh-key") else "ssh-key"


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
    auth_override: str = "",
) -> None:
    """Create a board pass (plaintext for Entra ID, encrypted for SSH-key)."""
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

    # Verify the VM exists before generating a pass
    vm_check = subprocess.run(
        ["az", "vm", "show", "--resource-group", rg, "--name", vm, "--query", "name", "-o", "tsv"],
        capture_output=True,
        text=True,
        check=False,
    )
    if vm_check.returncode != 0 or not vm_check.stdout.strip():
        con.error(f"VM not found: {vm} in {rg}")
        con.info("Check the developer name and environment are correct.")
        con.info(f"List VMs with: board vm ls --env {environment}")
        return

    # Auth method: override or auto-detect from VM tag
    if auth_override in ("entra-id", "ssh-key"):
        auth_method = auth_override
        con.info(f"Auth method: {auth_method} (forced)")
    else:
        auth_method = _resolve_auth_method(rg, vm)
        con.info(f"Auth method: {auth_method}")

    # Read SSH keys (only needed for ssh-key auth)
    private_key = ""
    public_key = ""
    key_path = cfg.ssh_key_path_expanded(name)

    if auth_method == "ssh-key":
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

    # Build payload
    from board.bundle.payload import build_payload

    payload = build_payload(
        developer_name=name,
        environment=environment,
        region=region,
        region_short=region_short,
        hostname=fqdn,
        username="devuser",
        auth_method=auth_method,
        ssh_private_key=private_key,
        ssh_public_key=public_key,
        resource_group=rg,
        vm_name=vm,
    )

    # TODO: populate browserIde in payload once code-server password or
    # VS Code tunnel URL provisioning is implemented. The extension already
    # handles the browserIde field if present — see bundle.ts step 10b.

    payload_json = payload.model_dump_json(by_alias=True)

    if auth_method == "entra-id":
        # Entra ID: plaintext envelope — no passphrase needed
        from board.bundle.crypto import wrap_plaintext

        envelope = wrap_plaintext(payload_json)
    else:
        # SSH-key: encrypted envelope — passphrase required
        passphrase = await prompts.secret("Passphrase for board pass (min 8 chars)")
        if len(passphrase) < 8:
            con.error("Passphrase must be at least 8 characters.")
            return

        passphrase_confirm = await prompts.secret("Confirm passphrase")
        if passphrase != passphrase_confirm:
            con.error("Passphrases do not match.")
            return

        from board.bundle.crypto import encrypt

        envelope = encrypt(payload_json, passphrase)

    # Write .board-pass file
    output_dir = Path.cwd()
    pass_filename = f"{name}.board-pass"
    pass_path = output_dir / pass_filename

    # Exclude empty strings and None to keep the envelope clean:
    # encrypted envelopes omit authMethod/payload, plaintext omit salt/iv/ciphertext/tag
    envelope_dict = {
        k: v
        for k, v in envelope.model_dump(by_alias=True).items()
        if v not in ("", None)
    }
    pass_path.write_text(json.dumps(envelope_dict, indent=2))

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
            auth_method=auth_method,
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
        auth_method=auth_method,
        filename=bundle_filename,
        issued_at=payload.issued_at or "",
        valid_until=payload.valid_until or "",
    )

    con.info(f"Send {bundle_filename} to {name}.")
    if auth_method == "entra-id":
        con.info("No passphrase needed — Entra ID handles authentication.")
        if vsix_path:
            con.info("They unzip it, double-click 'Setup Board', and click Connect — done.")
    else:
        con.info("Share the passphrase separately (different channel).")
        if vsix_path:
            con.info("They unzip it, double-click 'Setup Board', enter the passphrase — done.")


def export_pass_command(
    name: str = typer.Argument("", help="Developer name (e.g. jbloggs)."),
    environment: str = typer.Option("", "--env", help="Environment name."),
    region: str = typer.Option("", "--region", help="Azure region."),
    region_short: str = typer.Option("", "--region-short", help="Short region code."),
    auth: str = typer.Option(
        "",
        "--auth",
        help="Force auth method: entra-id or ssh-key (default: auto-detect from VM tag).",
    ),
) -> None:
    """Create a board pass for a developer."""
    asyncio.run(_run_export_pass(name, environment, region, region_short, auth_override=auth))
