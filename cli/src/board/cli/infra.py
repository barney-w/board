"""board infrastructure commands — create-vm, validate, what-if, destroy, preflight.

These are the lower-level "expert" entry points; most users want ``board up``.
All commands operate on a pre-existing resource group passed via ``--rg`` (or
``BOARD_RG``). Board never creates resource groups.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime

import typer

from board.core import config as cfg
from board.ui import console as con


def _resolve_rg(rg_arg: str = "") -> str:
    rg = rg_arg or os.environ.get("BOARD_RG", "")
    if not rg:
        con.error("Resource group is required. Pass --rg or set BOARD_RG.")
        raise typer.Exit(1)
    return rg


def _rg_location(rg: str) -> str:
    """Look up the resource group's location."""
    result = subprocess.run(  # noqa: S603, S607
        ["az", "group", "show", "--name", rg, "--query", "location", "-o", "tsv"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        con.error(f"Could not resolve location for resource group '{rg}'.")
        raise typer.Exit(1)
    return result.stdout.strip()


def create_vm_command(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
    sku: str = typer.Option("Standard_D2s_v6", "--sku", help="VM SKU."),
    preset: str = typer.Option(
        "",
        "--preset",
        help="Path to a .bicepparam preset file with extra defaults.",
    ),
) -> None:
    """Deploy a VM directly via Bicep (no wizard)."""
    rg_name = _resolve_rg(rg)
    location = _rg_location(rg_name)

    # Resolve SSH public key
    key_path = cfg.ssh_key_path_expanded(name)
    pub_path = key_path.with_suffix(".pub")
    if not pub_path.exists():
        con.error(f"SSH public key not found: {pub_path}")
        con.info(f"Generate one with: board vm keygen {name}")
        raise typer.Exit(1)
    ssh_pub_key = pub_path.read_text().strip()
    con.info(f"Using SSH key from {pub_path}")

    # Clear stale known_hosts entry
    fqdn = cfg.hostname(name, location)
    subprocess.run(["ssh-keygen", "-R", fqdn], capture_output=True, check=False)  # noqa: S603, S607

    # Find Bicep template
    infra_dir = cfg._find_infra_dir()
    bicep_file = infra_dir / "main.bicep"

    ts = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    cmd = [
        "az",
        "deployment",
        "group",
        "create",
        "--resource-group",
        rg_name,
        "--template-file",
        str(bicep_file),
        "--parameters",
        f"developerName={name}",
        f"vmSku={sku}",
        f"adminSshPublicKey={ssh_pub_key}",
        "--name",
        f"deploy-{name}-{ts}",
        "--verbose",
    ]
    if preset:
        cmd.extend(["--parameters", preset])

    con.info(f"Deploying board for {name} into {rg_name}...")
    result = subprocess.run(cmd, check=False)  # noqa: S603
    if result.returncode != 0:
        con.error("Deployment failed.")
        raise typer.Exit(1)
    con.success(f"Board deployed. Run: board vm ssh {name} --rg {rg_name}")


def validate_command(
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
    preset: str = typer.Option("", "--preset", help="Path to a .bicepparam preset file."),
) -> None:
    """Validate Bicep templates without deploying."""
    rg_name = _resolve_rg(rg)
    infra_dir = cfg._find_infra_dir()

    cmd = [
        "az",
        "deployment",
        "group",
        "validate",
        "--resource-group",
        rg_name,
        "--template-file",
        str(infra_dir / "main.bicep"),
    ]
    if preset:
        cmd.extend(["--parameters", preset])

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode == 0:
        con.success("Template is valid")
    else:
        con.error("Validation failed")
        if result.stderr:
            con.console.print(result.stderr)
        raise typer.Exit(1)


def what_if_command(
    name: str = typer.Argument(..., help="Developer name."),
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
    preset: str = typer.Option("", "--preset", help="Path to a .bicepparam preset file."),
) -> None:
    """Preview deployment changes (az deployment what-if)."""
    rg_name = _resolve_rg(rg)
    infra_dir = cfg._find_infra_dir()

    cmd = [
        "az",
        "deployment",
        "group",
        "what-if",
        "--resource-group",
        rg_name,
        "--template-file",
        str(infra_dir / "main.bicep"),
        "--parameters",
        f"developerName={name}",
    ]
    if preset:
        cmd.extend(["--parameters", preset])

    subprocess.run(cmd, check=False)  # noqa: S603


def destroy_command(
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete every board-managed resource inside the RG (NOT the RG itself)."""
    rg_name = _resolve_rg(rg)

    if not yes:
        con.warn(f"This will delete every board resource inside {rg_name}.")
        con.warn("The resource group itself will NOT be deleted.")
        typed = con.console.input("[bold]Type the resource group name to confirm: [/bold]")
        if typed.strip() != rg_name:
            con.info("Cancelled.")
            return

    # Check if RG exists
    result = subprocess.run(  # noqa: S603, S607
        ["az", "group", "show", "--name", rg_name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        con.info(f"Resource group {rg_name} does not exist.")
        _purge_orphaned_vaults(rg_name)
        return

    # Discover Key Vaults inside the RG before deleting (to purge soft-deleted ones after).
    kv_result = subprocess.run(  # noqa: S603, S607
        ["az", "keyvault", "list", "--resource-group", rg_name, "--query", "[].name", "-o", "tsv"],
        capture_output=True,
        text=True,
    )
    kv_names = (
        [v for v in kv_result.stdout.strip().split("\n") if v] if kv_result.stdout.strip() else []
    )

    # Delete only board-tagged resources to avoid wiping out unrelated resources
    # that happen to share the RG.
    con.info(f"Deleting board-managed resources in {rg_name}...")
    list_cmd = subprocess.run(  # noqa: S603, S607
        [
            "az",
            "resource",
            "list",
            "--resource-group",
            rg_name,
            "--query",
            "[?tags.\"managed-by\"=='bicep' || tags.\"managed-by\"=='board-cli'].id",
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    resource_ids = [r for r in list_cmd.stdout.strip().split("\n") if r]
    if not resource_ids:
        con.info("No board-managed resources found.")
    else:
        delete_result = subprocess.run(  # noqa: S603, S607
            ["az", "resource", "delete", "--ids", *resource_ids],
            check=False,
        )
        if delete_result.returncode != 0:
            con.error(f"Resource deletion failed (exit {delete_result.returncode}).")
            raise typer.Exit(1)
        con.success(f"Deleted {len(resource_ids)} board-managed resources")

    for kv in kv_names:
        con.info(f"Purging soft-deleted Key Vault: {kv}")
        subprocess.run(  # noqa: S603, S607
            ["az", "keyvault", "purge", "--name", kv],
            capture_output=True,
            check=False,
        )
    if kv_names:
        con.success("Key Vault purge complete")


def _purge_orphaned_vaults(rg: str) -> None:
    """Purge any orphaned soft-deleted Key Vaults from a resource group."""
    result = subprocess.run(  # noqa: S603, S607
        [
            "az",
            "keyvault",
            "list-deleted",
            "--query",
            f"[?properties.vaultId && contains(properties.vaultId, '{rg}')].name",
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
    )
    for kv in [
        v for v in (result.stdout.strip().split("\n") if result.stdout.strip() else []) if v
    ]:
        con.info(f"Purging orphaned soft-deleted Key Vault: {kv}")
        subprocess.run(  # noqa: S603, S607
            ["az", "keyvault", "purge", "--name", kv],
            capture_output=True,
            check=False,
        )


def preflight_command(
    name: str = typer.Argument(..., help="Developer name."),
    rg: str = typer.Option("", "--rg", help="Resource group (or set BOARD_RG)."),
    sku: str = typer.Option("Standard_D2s_v6", "--sku", help="VM SKU."),
) -> None:
    """Pre-deployment validation checks."""
    rg_name = _resolve_rg(rg)
    vm_full = cfg.vm_name(rg_name, name)

    passed = 0
    failed = 0

    def ok(msg: str) -> None:
        nonlocal passed
        con.success(msg)
        passed += 1

    def fail(msg: str, fix: str) -> None:
        nonlocal failed
        con.error(msg)
        con.info(f"  Fix: {fix}")
        failed += 1

    con.header(f"Preflight checks for {name}")

    # 1. Azure CLI
    if (
        subprocess.run(  # noqa: S603, S607
            ["az", "--version"], capture_output=True
        ).returncode
        == 0
    ):
        ok("Azure CLI installed")
    else:
        fail("Azure CLI not found", "brew install azure-cli")

    # 2. Logged in
    acct = subprocess.run(  # noqa: S603, S607
        ["az", "account", "show", "--query", "name", "-o", "tsv"],
        capture_output=True,
        text=True,
    )
    if acct.returncode == 0:
        ok(f"Azure CLI logged in ({acct.stdout.strip()})")
    else:
        fail("Not logged in to Azure", "az login")

    # 3. Resource group
    if (
        subprocess.run(  # noqa: S603, S607
            ["az", "group", "show", "--name", rg_name], capture_output=True
        ).returncode
        == 0
    ):
        ok(f"Resource group {rg_name} exists")
    else:
        fail(f"Resource group {rg_name} not found", f"Ask an admin to create '{rg_name}'")

    # 4. SSH key
    key_path = cfg.ssh_key_path_expanded(name)
    if key_path.exists():
        ok(f"SSH key exists: {key_path}")
    else:
        fail(f"SSH key not found: {key_path}", f"board vm keygen {name}")

    # 5. Developer name validation
    if cfg.validate_developer_name(name):
        ok(f"Developer name '{name}' is valid")
    else:
        fail(
            f"Developer name '{name}' is invalid",
            "Lowercase letters/numbers, 1-12 chars, start with letter",
        )

    # 6. No existing VM
    if (
        subprocess.run(  # noqa: S603, S607
            ["az", "vm", "show", "--resource-group", rg_name, "--name", vm_full],
            capture_output=True,
        ).returncode
        != 0
    ):
        ok(f"No existing VM named {vm_full}")
    else:
        fail(f"VM {vm_full} already exists", f"board vm delete {name} or choose a different name")

    con.divider()
    con.info(f"Results: {passed} passed, {failed} failed")
    if failed > 0:
        con.error("Fix the issues above before deploying.")
        raise typer.Exit(1)
    con.info(f"Ready: board create-vm {name} --rg {rg_name} --sku {sku}")
