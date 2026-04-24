"""board admin — interactive admin control panel."""

from __future__ import annotations

import asyncio
from pathlib import Path

from board.core import config as cfg
from board.core.errors import BoardError, SSHError
from board.models.deployment import LlmConfig
from board.ui import console as con
from board.ui import prompts

DEFAULT_LOCATION = "australiaeast"
DEFAULT_REGION = "aue"


async def _select_env() -> str:
    """Pick an environment from discovered bicepparams."""
    params = cfg.discover_bicepparams()
    env_names = [name for name, _ in params]

    if not env_names:
        con.error("No environments found in infra/config/")
        return ""

    if len(env_names) == 1:
        con.info(f"Auto-selected environment: {env_names[0]}")
        return env_names[0]

    return await prompts.choose("Select environment:", env_names)


async def _select_vm(environment: str) -> tuple[str, str]:
    """Pick a VM from the resource group. Returns (vm_name, rg_name)."""
    rg_name = cfg.resource_group(environment, DEFAULT_REGION)

    from board.azure.auth import get_credential, get_subscription_id
    from board.azure.compute import list_vms

    credential = get_credential()
    sub_id = await get_subscription_id()

    with con.spin("Loading VMs..."):
        vms = await list_vms(credential, sub_id, rg_name)

    if not vms:
        con.info(f"No VMs found in resource group {rg_name}")
        return "", rg_name

    if len(vms) == 1:
        vm = vms[0]
        con.info(f"Auto-selected VM: {vm['name']} ({vm['power_state']})")
        return vm["name"], rg_name

    display = [f"{vm['name']}  ({vm['power_state']}, {vm['vm_size']})" for vm in vms]
    chosen = await prompts.choose("Select a VM:", display)
    vm_name = chosen.split("  ")[0]
    return vm_name, rg_name


def _derive_dev_name(vm_name: str) -> str:
    """Extract dev name from VM name pattern: vm-<env>-<region>-devvm-<name>."""
    return vm_name.rsplit("-", 1)[-1] if "-" in vm_name else vm_name


async def _manage_vms() -> None:
    """VM management submenu."""
    environment = await _select_env()
    if not environment:
        return

    vm_name, rg_name = await _select_vm(environment)
    if not vm_name:
        return

    dev_name = _derive_dev_name(vm_name)
    fqdn = cfg.hostname(dev_name, DEFAULT_LOCATION)
    key_path = cfg.ssh_key_path_expanded(dev_name)

    from board.azure.auth import get_credential, get_subscription_id
    from board.azure.compute import deallocate_vm, delete_vm, start_vm

    credential = get_credential()
    sub_id = await get_subscription_id()

    while True:
        con.summary_box(
            f"VM: {vm_name}",
            [f"Developer: {dev_name}", f"FQDN:      {fqdn}", f"Key:       {key_path}"],
        )

        vm_action = await prompts.choose(
            "VM action:",
            ["Start", "Stop (deallocate)", "SSH into VM", "Delete VM", "Back"],
        )

        if "Start" in vm_action:
            with con.spin(f"Starting {vm_name}..."):
                await start_vm(credential, sub_id, rg_name, vm_name)
            con.success("VM started")
        elif "Stop" in vm_action:
            with con.spin(f"Deallocating {vm_name}..."):
                await deallocate_vm(credential, sub_id, rg_name, vm_name)
            con.success("VM deallocated")
        elif "SSH" in vm_action:
            con.info(f"Connecting to {fqdn}...")
            import subprocess

            subprocess.run(  # noqa: S603, S607
                ["ssh", "-i", str(key_path), f"devuser@{fqdn}"],
                check=False,
            )
        elif "Delete" in vm_action:
            con.warn(f"This will permanently delete VM {vm_name} and its associated resources.")
            if await prompts.confirm(f"Are you sure you want to delete {vm_name}?", default=False):
                with con.spin(f"Deleting {vm_name}..."):
                    await delete_vm(credential, sub_id, rg_name, vm_name)
                con.success(f"VM {vm_name} deleted")
                return
            else:
                con.info("Delete cancelled")
        elif "Back" in vm_action:
            return


async def _provision_projects_menu() -> None:
    """Set up projects on an existing VM."""
    environment = await _select_env()
    if not environment:
        return

    vm_name, rg_name = await _select_vm(environment)
    if not vm_name:
        return

    dev_name = _derive_dev_name(vm_name)
    fqdn = cfg.hostname(dev_name, DEFAULT_LOCATION)
    key_path = cfg.ssh_key_path_expanded(dev_name)

    # Find manifests
    manifest_dir = Path.cwd()
    for parent in [manifest_dir, *manifest_dir.parents]:
        candidate = parent / "projects"
        if candidate.is_dir():
            manifest_dir = candidate
            break

    from board.core.manifest import list_projects

    project_list = list_projects(manifest_dir)
    if not project_list:
        con.error(f"No project manifests found in {manifest_dir}")
        return

    project_names = [name for name, _ in project_list]
    selected = await prompts.checklist("Select projects to provision:", project_names)
    if not selected:
        con.warn("No projects selected")
        return

    kv_name = await prompts.input_text("Key Vault name (Enter to skip)", default="")

    # LLM provider
    llm_config = LlmConfig()
    llm_choice = await prompts.choose(
        "LLM provider for projects:",
        [
            "Azure AI Foundry (Claude via Azure)",
            "Anthropic API (direct)",
            "Skip (configure later)",
        ],
    )
    if "Foundry" in llm_choice:
        foundry_endpoint = await prompts.input_text("Foundry endpoint URL", default="")
        if foundry_endpoint:
            foundry_key = await prompts.secret("Foundry API key")
            if foundry_key:
                llm_config = LlmConfig(
                    provider="foundry",
                    api_key=foundry_key,
                    endpoint=foundry_endpoint.rstrip("/"),
                )
    elif "Anthropic" in llm_choice:
        anthropic_key = await prompts.secret("Anthropic API key")
        if anthropic_key:
            llm_config = LlmConfig(provider="anthropic", api_key=anthropic_key)

    con.info(f"Provisioning projects: {' '.join(selected)}")
    con.info(f"Target: devuser@{fqdn}")

    from board.provision.orchestrator import provision_projects
    from board.ssh.session import SSHSession

    try:
        async with SSHSession() as ssh:
            await ssh.connect(fqdn, username="devuser", key_path=key_path)
            success_count, fail_count = await provision_projects(
                ssh=ssh,
                manifest_dir=manifest_dir,
                console=con.console,
                keyvault_name=kv_name,
                filter_names=selected,
                llm_config=llm_config,
            )
            con.success(f"Done: {success_count} succeeded, {fail_count} failed")
    except (SSHError, BoardError) as exc:
        con.error(f"Provisioning failed: {exc}")


async def _export_bundle_menu() -> None:
    """Create a board pass."""
    environment = await _select_env()
    if not environment:
        return

    vm_name, _ = await _select_vm(environment)
    if not vm_name:
        return

    dev_name = _derive_dev_name(vm_name)

    from board.cli.export_pass import _run_export_pass

    await _run_export_pass(
        name=dev_name,
        environment=environment,
        region=DEFAULT_LOCATION,
        region_short=DEFAULT_REGION,
    )

    con.divider()
    con.warn("Remember: send the .board-pass file and passphrase via SEPARATE channels.")
    con.info("  e.g. file via Teams, passphrase verbally or via a different channel.")


async def _manage_secrets() -> None:
    """Key Vault secrets management."""
    kv_name = await prompts.input_text("Key Vault name", default="kv-devvm-secrets")

    from board.azure.auth import get_credential
    from board.azure.keyvault import list_secrets, set_secret

    credential = get_credential()
    vault_url = f"https://{kv_name}.vault.azure.net/"

    try:
        with con.spin("Checking Key Vault..."):
            existing = await list_secrets(vault_url, credential)
        con.success(f"Key Vault '{kv_name}' accessible ({len(existing)} secrets)")
    except Exception as exc:
        con.warn(f"Key Vault '{kv_name}' not accessible: {exc}")
        return

    while True:
        con.info(f"Secrets in {kv_name}: {', '.join(existing) if existing else '(none)'}")

        action = await prompts.choose(
            "What would you like to do?",
            ["Set a secret", "Back"],
        )

        if "Set" in action:
            secret_name = await prompts.input_text("Secret name")
            if not secret_name:
                con.warn("No secret name provided")
                continue
            secret_value = await prompts.secret(f"Value for {secret_name}")
            if secret_value:
                await set_secret(vault_url, credential, secret_name, secret_value)
                con.success(f"Secret '{secret_name}' set")
                if secret_name not in existing:
                    existing.append(secret_name)
        elif "Back" in action:
            return


async def _health_checks() -> None:
    """Run health checks on a VM."""
    environment = await _select_env()
    if not environment:
        return

    vm_name, _ = await _select_vm(environment)
    if not vm_name:
        return

    dev_name = _derive_dev_name(vm_name)
    fqdn = cfg.hostname(dev_name, DEFAULT_LOCATION)

    con.info(f"Running health checks on board {fqdn}...")

    from board.cli.validate import _run_smoke_test

    await _run_smoke_test(name=dev_name)


async def _run_admin() -> None:
    """Main admin control panel loop."""
    while True:
        con.banner("Board Control", "Manage boards, projects, and secrets")

        action = await prompts.choose(
            "What do you want to do?",
            [
                "Manage boards",
                "Set up projects",
                "Create a board pass",
                "Manage Key Vault secrets",
                "Run health checks",
                "Exit",
            ],
        )

        try:
            if "Manage boards" in action:
                await _manage_vms()
            elif "Set up projects" in action:
                await _provision_projects_menu()
            elif "board pass" in action:
                await _export_bundle_menu()
            elif "Key Vault" in action:
                await _manage_secrets()
            elif "health" in action:
                await _health_checks()
            elif "Exit" in action:
                return
        except KeyboardInterrupt:
            con.warn("Cancelled.")
        except BoardError as exc:
            con.error(str(exc))


def admin_command() -> None:
    """Open the admin control panel for managing boards."""
    asyncio.run(_run_admin())
