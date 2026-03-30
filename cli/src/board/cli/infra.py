"""board infrastructure commands — create-rg, create-vm, validate, what-if, destroy, preflight."""

from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import UTC, datetime

import typer

from board.core import config as cfg
from board.ui import console as con

DEFAULT_LOCATION = "australiaeast"
DEFAULT_REGION = "aue"


def _resolve_env(env: str = "") -> str:
    return env or os.environ.get("BOARD_ENVIRONMENT", "personal")


def create_rg_command(
    env: str = typer.Option("", "--env", help="Environment name."),
    location: str = typer.Option(DEFAULT_LOCATION, "--location", help="Azure region."),
    region_short: str = typer.Option(DEFAULT_REGION, "--region-short", help="Short region code."),
) -> None:
    """Create the resource group (idempotent)."""

    async def _run() -> None:
        environment = _resolve_env(env)
        rg = cfg.resource_group(environment, region_short)

        from board.azure.auth import get_credential, get_subscription_id
        from board.azure.deployment import ensure_resource_group

        credential = get_credential()
        sub_id = await get_subscription_id()

        with con.spin(f"Creating resource group {rg}..."):
            await ensure_resource_group(
                credential,
                sub_id,
                rg,
                location,
                tags={"project": "devvm", "environment": environment, "managed-by": "bicep"},
            )
        con.success(f"Resource group {rg} ready")

    asyncio.run(_run())


def create_vm_command(
    name: str = typer.Argument(..., help="Developer name (e.g. jbloggs)."),
    env: str = typer.Option("", "--env", help="Environment name."),
    sku: str = typer.Option("Standard_D2s_v6", "--sku", help="VM SKU."),
    location: str = typer.Option(DEFAULT_LOCATION, "--location", help="Azure region."),
    region_short: str = typer.Option(DEFAULT_REGION, "--region-short", help="Short region code."),
) -> None:
    """Deploy a VM directly via Bicep (no wizard)."""
    environment = _resolve_env(env)
    rg = cfg.resource_group(environment, region_short)

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

    # Find Bicep template and params
    infra_dir = cfg._find_infra_dir()
    bicep_file = infra_dir / "main.bicep"
    bicep_params = cfg.discover_bicepparams(infra_dir)
    param_file = None
    for pname, ppath in bicep_params:
        if pname == environment:
            param_file = ppath
            break

    ts = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    cmd = [
        "az",
        "deployment",
        "group",
        "create",
        "--resource-group",
        rg,
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
    if param_file:
        cmd.insert(cmd.index("--parameters"), "--parameters")
        cmd.insert(cmd.index("--parameters") + 1, str(param_file))

    con.info(f"Deploying board for {name} in {environment}...")
    result = subprocess.run(cmd, check=False)  # noqa: S603
    if result.returncode != 0:
        con.error("Deployment failed.")
        raise typer.Exit(1)
    con.success(f"Board deployed. Run: board vm ssh {name}")


def validate_command(
    env: str = typer.Option("", "--env", help="Environment name."),
    region_short: str = typer.Option(DEFAULT_REGION, "--region-short", help="Short region code."),
) -> None:
    """Validate Bicep templates without deploying."""
    environment = _resolve_env(env)
    rg = cfg.resource_group(environment, region_short)
    infra_dir = cfg._find_infra_dir()

    params = cfg.discover_bicepparams(infra_dir)
    param_file = None
    for pname, ppath in params:
        if pname == environment:
            param_file = ppath
            break

    cmd = [
        "az",
        "deployment",
        "group",
        "validate",
        "--resource-group",
        rg,
        "--template-file",
        str(infra_dir / "main.bicep"),
    ]
    if param_file:
        cmd.extend(["--parameters", str(param_file)])

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
    env: str = typer.Option("", "--env", help="Environment name."),
    region_short: str = typer.Option(DEFAULT_REGION, "--region-short", help="Short region code."),
) -> None:
    """Preview deployment changes (az deployment what-if)."""
    environment = _resolve_env(env)
    rg = cfg.resource_group(environment, region_short)
    infra_dir = cfg._find_infra_dir()

    params = cfg.discover_bicepparams(infra_dir)
    param_file = None
    for pname, ppath in params:
        if pname == environment:
            param_file = ppath
            break

    cmd = [
        "az",
        "deployment",
        "group",
        "what-if",
        "--resource-group",
        rg,
        "--template-file",
        str(infra_dir / "main.bicep"),
        "--parameters",
        f"developerName={name}",
    ]
    if param_file:
        cmd.extend(["--parameters", str(param_file)])

    subprocess.run(cmd, check=False)  # noqa: S603


def destroy_command(
    env: str = typer.Option("", "--env", help="Environment name."),
    region_short: str = typer.Option(DEFAULT_REGION, "--region-short", help="Short region code."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete entire environment (resource group + purge Key Vaults)."""
    environment = _resolve_env(env)
    rg = cfg.resource_group(environment, region_short)

    if not yes:
        con.warn(f"This will delete the ENTIRE resource group {rg}.")
        typed = con.console.input("[bold]Type the resource group name to confirm: [/bold]")
        if typed.strip() != rg:
            con.info("Cancelled.")
            return

    # Check if RG exists
    result = subprocess.run(  # noqa: S603, S607
        ["az", "group", "show", "--name", rg],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        con.info(f"Resource group {rg} does not exist.")
        _purge_orphaned_vaults(rg)
        return

    # Discover Key Vaults before deleting
    kv_result = subprocess.run(  # noqa: S603, S607
        ["az", "keyvault", "list", "--resource-group", rg, "--query", "[].name", "-o", "tsv"],
        capture_output=True,
        text=True,
    )
    kv_names = (
        [v for v in kv_result.stdout.strip().split("\n") if v] if kv_result.stdout.strip() else []
    )

    con.info(f"Deleting resource group {rg}...")
    delete_result = subprocess.run(  # noqa: S603, S607
        ["az", "group", "delete", "--name", rg, "--yes"],
        check=False,
    )
    if delete_result.returncode in (130, 2):
        con.info("Wait cancelled -- deletion still running server-side on Azure.")
        con.info(f"Check: az group show --name {rg} --query properties.provisioningState -o tsv")
        return
    elif delete_result.returncode != 0:
        con.error(f"Resource group deletion failed (exit {delete_result.returncode}).")
        raise typer.Exit(1)

    con.success(f"Resource group {rg} deleted")

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
    env: str = typer.Option("", "--env", help="Environment name."),
    sku: str = typer.Option("Standard_D2s_v6", "--sku", help="VM SKU."),
    location: str = typer.Option(DEFAULT_LOCATION, "--location", help="Azure region."),
    region_short: str = typer.Option(DEFAULT_REGION, "--region-short", help="Short region code."),
) -> None:
    """Pre-deployment validation checks."""
    environment = _resolve_env(env)
    rg = cfg.resource_group(environment, region_short)
    vm_full = cfg.vm_name(environment, region_short, name)

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
            ["az", "group", "show", "--name", rg], capture_output=True
        ).returncode
        == 0
    ):
        ok(f"Resource group {rg} exists")
    else:
        fail(f"Resource group {rg} not found", f"board create-rg --env {environment}")

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
            ["az", "vm", "show", "--resource-group", rg, "--name", vm_full],
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
    con.info(f"Ready: board create-vm {name} --env {environment} --sku {sku} --location {location}")
