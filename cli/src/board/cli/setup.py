"""board up — 5-phase setup wizard for provisioning a new developer VM."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import typer

from board.core import config as cfg
from board.core.errors import BoardError, DeploymentError, SSHError
from board.models.deployment import DeploymentConfig
from board.ui import console as con
from board.ui import prompts

# ── VM Size catalog ──

VM_SIZE_CATALOG = [
    {"sku": "Standard_D2s_v6", "label": "Standard_D2s_v6  -- 2 vCPU,  8 GB RAM", "cost": "~55"},
    {"sku": "Standard_D4s_v6", "label": "Standard_D4s_v6  -- 4 vCPU, 16 GB RAM", "cost": "~110"},
    {"sku": "Standard_D8s_v6", "label": "Standard_D8s_v6  -- 8 vCPU, 32 GB RAM", "cost": "~220"},
]

DEFAULT_LOCATION = "australiaeast"
DEFAULT_REGION = "aue"
TOTAL_STEPS = 5


def _resolve_location(location: str) -> str:
    return location or os.environ.get("BOARD_LOCATION", DEFAULT_LOCATION)


def _resolve_region_short(region_short: str) -> str:
    return region_short or os.environ.get("BOARD_REGION_SHORT", DEFAULT_REGION)


def _resolve_env(env: str) -> str:
    return env or os.environ.get("BOARD_ENVIRONMENT", "")


def _vm_size_options() -> list[str]:
    """Build the VM size menu options."""
    options = []
    for entry in VM_SIZE_CATALOG:
        options.append(f"{entry['label']}  (${entry['cost']}/mo)")
    options.append("Custom -- enter a SKU manually")
    return options


def _sku_from_label(label: str) -> str:
    """Extract the SKU name from a menu label."""
    for entry in VM_SIZE_CATALOG:
        if label.startswith(entry["label"]):
            return entry["sku"]
    return "custom"


def _cost_from_sku(sku: str) -> str:
    for entry in VM_SIZE_CATALOG:
        if entry["sku"] == sku:
            return f"${entry['cost']}"
    return "unknown"


def _find_manifest_dir() -> Path:
    """Locate the projects/ manifest directory."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "projects"
        if candidate.is_dir() and list(candidate.glob("*.project.yaml")):
            return candidate
    return cwd / "projects"


async def _run_up(
    dry_run: bool,
    demo: bool,
    non_interactive: bool,
    env: str,
    location: str,
    region_short: str,
) -> None:
    """Async implementation of the up command."""
    location = _resolve_location(location)
    region_short = _resolve_region_short(region_short)
    env_override = _resolve_env(env)

    if non_interactive:
        os.environ["BOARD_NON_INTERACTIVE"] = "1"

    # ══════════════════════════════════════════════════
    # [1/5] Configure
    # ══════════════════════════════════════════════════

    con.ascii_banner("shape a new board")
    con.step(1, TOTAL_STEPS, "Configure")

    # Persona
    persona = await prompts.choose(
        "Who is this board for?",
        ["Myself", "Another developer"],
        default="Myself",
    )
    is_self = persona == "Myself"
    name_prompt = "Your name" if is_self else "Developer's name"

    # Developer name
    env_dev_name = os.environ.get("BOARD_DEV_NAME", "")
    if non_interactive and env_dev_name:
        dev_name = env_dev_name
        con.success(f"Developer: {dev_name}")
    else:
        con.info("Use initial + last name, lowercase (e.g. jbloggs, asmith, cjones)")
        dev_name = await prompts.input_validated(
            name_prompt,
            default=env_dev_name,
            pattern=r"^[a-z][a-z0-9]{0,11}$",
            message="Must be lowercase, start with a letter, alphanumeric only, max 12 chars",
        )

    # Environment
    bicepparams = cfg.discover_bicepparams()
    env_names = [name for name, _ in bicepparams]

    if env_override and env_override in env_names:
        environment = env_override
        con.info(f"Environment: {environment}")
    elif len(env_names) == 1:
        environment = env_names[0]
        con.info(f"Environment: {environment}")
    elif env_names:
        environment = await prompts.choose("Environment:", env_names)
    else:
        environment = "personal"
        con.info(f"Environment: {environment} (no bicepparam files found)")

    # Derived names
    deploy_cfg = DeploymentConfig(
        developer_name=dev_name,
        environment=environment,
        region=location,
        region_short=region_short,
    )

    # Project selection
    manifest_dir = _find_manifest_dir()
    selected_projects: list[str] = []
    kv_name = ""
    create_kv = False

    if manifest_dir.is_dir():
        from board.core.manifest import list_projects

        project_list = list_projects(manifest_dir)
        if project_list:
            display_choices = [f"{name} -- {desc}" for name, desc in project_list]
            display_choices.append("None -- empty ~/projects")

            all_defaults = [c for c in display_choices if not c.startswith("None")]
            selected = await prompts.checklist(
                "Projects to install:",
                display_choices,
                defaults=all_defaults,
            )
            for item in selected:
                if item.startswith("None"):
                    continue
                proj_name = item.split(" -- ")[0].strip()
                selected_projects.append(proj_name)

            if selected_projects:
                con.success(f"Projects: {' '.join(selected_projects)}")
            else:
                con.info("No projects selected")

    # Key Vault
    if selected_projects:
        all_kv_secrets: set[str] = set()
        from board.core.manifest import load_all as load_manifests

        manifests = load_manifests(manifest_dir, filter_names=selected_projects)
        for m in manifests:
            if m.env and m.env.keyvault_secrets:
                all_kv_secrets.update(m.env.keyvault_secrets.values())

        if all_kv_secrets and not non_interactive:
            kv_choice = await prompts.choose(
                "These projects use secrets from Key Vault:",
                ["Use existing Key Vault", "Create new Key Vault", "Skip for now"],
            )
            if "existing" in kv_choice:
                kv_name = await prompts.input_text("Key Vault name")
            elif "Create" in kv_choice:
                kv_name = await prompts.input_text(
                    "Name for new Key Vault",
                    default=f"kv-devvm-{dev_name}",
                )
                create_kv = True
            else:
                con.info("Secrets can be added later with: board shape")

    # SSH key
    key_path = deploy_cfg.ssh_key_path_expanded
    ssh_pub_key = ""

    if non_interactive:
        if key_path.exists():
            ssh_pub_key = key_path.with_suffix(".pub").read_text().strip()
            con.success(f"Using existing SSH key: {key_path}")
        elif not dry_run:
            from board.ssh.keys import generate_keypair

            _, ssh_pub_key = await generate_keypair(key_path)
            con.success(f"Key generated: {key_path}")
        else:
            ssh_pub_key = "dry-run-placeholder"
            con.success(f"SSH key: would generate {key_path}")
    elif key_path.exists():
        con.success(f"Found SSH key: {key_path}")
        key_action = await prompts.choose(
            "SSH key:",
            [
                "Use existing key",
                "Generate a new key (overwrites existing)",
                "Use a different key file",
            ],
            default="Use existing key",
        )
        if "Generate" in key_action:
            from board.ssh.keys import generate_keypair

            _, ssh_pub_key = await generate_keypair(key_path)
            con.success(f"Key generated: {key_path}")
        elif "existing" in key_action:
            ssh_pub_key = key_path.with_suffix(".pub").read_text().strip()
            con.success("Using existing key")
        elif "different" in key_action:
            custom_key = await prompts.input_text(
                "Path to public key file",
                default=str(Path.home() / ".ssh" / "id_ed25519.pub"),
            )
            custom_path = Path(custom_key).expanduser()
            if not custom_path.exists():
                con.error(f"File not found: {custom_key}")
                raise typer.Exit(1)
            ssh_pub_key = custom_path.read_text().strip()
            key_path = custom_path.with_suffix("")
            con.success(f"Using key: {custom_key}")
    else:
        if dry_run:
            ssh_pub_key = "dry-run-placeholder"
            con.success(f"SSH key: would generate {key_path}")
        else:
            from board.ssh.keys import generate_keypair

            _, ssh_pub_key = await generate_keypair(key_path)
            con.success(f"Key generated: {key_path}")

    # VM size
    env_vm_sku = os.environ.get("BOARD_VM_SKU", "")
    if non_interactive:
        vm_sku = env_vm_sku or "Standard_D2s_v6"
        con.success(f"VM size: {vm_sku}")
    else:
        size_menu = _vm_size_options()
        vm_size_label = await prompts.choose("VM size:", size_menu)
        vm_sku = _sku_from_label(vm_size_label)
        if vm_sku == "custom":
            vm_sku = await prompts.input_text("Enter Azure VM SKU", default="Standard_D2s_v6")

    # ══════════════════════════════════════════════════
    # [2/5] Authenticate
    # ══════════════════════════════════════════════════

    con.step(2, TOTAL_STEPS, "Authenticate")

    if dry_run:
        con.success("Skipping authentication (dry run)")
    else:
        from board.azure.auth import get_subscription_id

        try:
            sub_id = await get_subscription_id()
            con.success(f"Subscription: {sub_id}")
        except RuntimeError as exc:
            con.error(str(exc))
            con.info("Run: az login")
            raise typer.Exit(1) from exc

    # ══════════════════════════════════════════════════
    # [3/5] Review
    # ══════════════════════════════════════════════════

    con.step(3, TOTAL_STEPS, "Review")

    cost_compute = _cost_from_sku(vm_sku)
    summary_lines = [
        f"Developer:     {dev_name}",
        f"Environment:   {environment}",
        f"VM Size:       {vm_sku}",
        f"Region:        {location}",
        "OS:            Ubuntu 24.04 LTS",
        "Disk:          128 GB Standard SSD",
        "Auto-shutdown: 19:00 AEST",
        "",
        "Estimated monthly cost:",
        f"  Compute (with auto-shutdown): {cost_compute}",
        "  Disk + Public IP:             ~$24",
        "",
        f"Resource group: {deploy_cfg.resource_group}",
        f"VM name:        {deploy_cfg.vm_name}",
    ]
    if selected_projects:
        summary_lines.append(f"Projects:       {' '.join(selected_projects)}")
    if kv_name:
        summary_lines.append(f"Key Vault:      {kv_name}")

    con.summary_box("Deployment Summary", summary_lines)

    if not await prompts.confirm("Shape this board?"):
        con.info("Cancelled.")
        raise typer.Exit(0)

    # ══════════════════════════════════════════════════
    # [4/5] Shape
    # ══════════════════════════════════════════════════

    con.step(4, TOTAL_STEPS, "Shape")

    if dry_run:
        con.success(f"[DRY RUN] Would create resource group: {deploy_cfg.resource_group}")
        con.success(f"[DRY RUN] Would deploy VM: {deploy_cfg.vm_name} ({vm_sku})")
        con.success(f"[DRY RUN] Location: {location}")
        if kv_name:
            con.success(f"[DRY RUN] Key Vault: {kv_name}")
        if selected_projects:
            con.success(f"[DRY RUN] Projects: {' '.join(selected_projects)}")
        con.success("[DRY RUN] Validation complete -- all inputs valid")
        raise typer.Exit(0)

    # ── Infrastructure ──
    phase_start = time.monotonic()
    provision_warnings: list[str] = []

    from board.azure.auth import get_credential, get_subscription_id
    from board.azure.deployment import deploy, ensure_resource_group

    credential = get_credential()
    sub_id = await get_subscription_id()

    try:
        with con.spin("Creating resource group..."):
            await ensure_resource_group(
                credential,
                sub_id,
                deploy_cfg.resource_group,
                location,
                tags={"project": "devvm", "environment": environment, "managed-by": "board-cli"},
            )
        con.success(f"Resource group: {deploy_cfg.resource_group}")
    except DeploymentError as exc:
        con.error(str(exc))
        raise typer.Exit(1) from exc

    # Key Vault creation
    kv_resource_id = ""
    if create_kv and kv_name:
        try:
            from board.azure.auth import get_tenant_id
            from board.azure.keyvault import create_or_recover_vault

            tenant_id = await get_tenant_id()

            with con.spin(f"Creating Key Vault: {kv_name}..."):
                await create_or_recover_vault(
                    credential,
                    sub_id,
                    deploy_cfg.resource_group,
                    kv_name,
                    location,
                    tenant_id,
                )
            con.success(f"Key Vault: {kv_name}")
        except BoardError as exc:
            con.warn(f"Key Vault creation issue: {exc}")
            provision_warnings.append(f"Key Vault: {exc}")

    # Bicep deployment
    infra_dir = cfg._find_infra_dir()
    bicep_file = infra_dir / "main.bicep"
    deploy_params = {
        "developerName": dev_name,
        "vmSku": vm_sku,
        "adminSshPublicKey": ssh_pub_key,
        "environment": environment,
    }
    if kv_resource_id:
        deploy_params["keyVaultResourceId"] = kv_resource_id

    try:
        from board.azure.deployment import bicep_build

        with con.spin("Compiling Bicep template..."):
            template = await bicep_build(bicep_file)
        con.success("Bicep compiled")

        deployment_name = f"board-{dev_name}-{int(time.time())}"
        con.info(f"Deployment: {deployment_name}")

        def _on_progress(resource: str, state: str) -> None:
            con.info(f"  {resource}: {state}")

        async with con.spin_timed("Deploying infrastructure"):
            outputs = await deploy(
                credential,
                sub_id,
                deploy_cfg.resource_group,
                template,
                parameters=deploy_params,
                deployment_name=deployment_name,
                on_progress=_on_progress,
            )
        deploy_elapsed = time.monotonic() - phase_start
        con.phase_timing("Infrastructure deployed", deploy_elapsed)
    except KeyboardInterrupt:
        con.warn("Interrupted.")
        con.info(f"Check deployment: az deployment group list -g {deploy_cfg.resource_group}")
        raise typer.Exit(130) from None
    except DeploymentError as exc:
        con.error(str(exc))
        raise typer.Exit(1) from exc

    # ── Cloud-init wait ──
    cloud_init_start = time.monotonic()
    cloud_init_ok = True

    try:
        from board.provision.cloud_init import wait_for_cloud_init

        public_ip = outputs.get("publicIpAddress", "") if outputs else ""
        async with con.spin_timed("Waiting for cloud-init"):
            await wait_for_cloud_init(
                deploy_cfg.hostname,
                str(key_path),
                user="devuser",
                fallback_ip=public_ip,
                console=con.console,
            )
        cloud_init_elapsed = time.monotonic() - cloud_init_start
        con.phase_timing("Tools installed", cloud_init_elapsed)
    except SSHError as exc:
        cloud_init_ok = False
        con.warn(f"Cloud-init did not complete: {exc}")
        con.info(f"After cloud-init finishes, run: board install-projects {dev_name}")
        provision_warnings.append("Cloud-init did not complete -- projects not installed")

    # ── Project provisioning ──
    if selected_projects and cloud_init_ok:
        provision_start = time.monotonic()
        con.info("Provisioning projects...")

        from board.provision.orchestrator import provision_projects
        from board.ssh.session import SSHSession

        try:
            async with SSHSession() as ssh:
                await ssh.connect(
                    deploy_cfg.hostname,
                    username="devuser",
                    key_path=key_path,
                )
                success_count, fail_count = await provision_projects(
                    ssh=ssh,
                    manifest_dir=manifest_dir,
                    console=con.console,
                    keyvault_name=kv_name,
                    filter_names=selected_projects,
                )
                if fail_count > 0:
                    provision_warnings.append("Some projects had issues")
            provision_elapsed = time.monotonic() - provision_start
            con.phase_timing("Projects provisioned", provision_elapsed)
        except (SSHError, BoardError) as exc:
            con.warn(f"Project provisioning failed: {exc}")
            provision_warnings.append(f"Provisioning: {exc}")

    # ══════════════════════════════════════════════════
    # [5/5] Handoff
    # ══════════════════════════════════════════════════

    con.step(5, TOTAL_STEPS, "Handoff")

    # SSH config
    from board.ssh.config_file import build_ssh_key_config_block, write_managed_block

    ssh_config_path = Path.home() / ".ssh" / "config"
    block = build_ssh_key_config_block(
        alias=deploy_cfg.ssh_host_alias,
        hostname=deploy_cfg.hostname,
        key_path=str(key_path),
    )
    write_managed_block(ssh_config_path, deploy_cfg.ssh_host_alias, block)
    con.success("SSH config ready")

    # Timing
    total_elapsed = time.monotonic() - phase_start
    total_min = int(total_elapsed) // 60
    total_sec = int(total_elapsed) % 60

    # Completion box
    if is_self:
        con.completion_box(
            f"{dev_name}'s board is ready",
            [
                f"Connect:  ssh {deploy_cfg.ssh_host_alias}",
                f"VS Code:  Remote-SSH > {deploy_cfg.ssh_host_alias}",
                "",
                "Daily:",
                f"  board vm start {dev_name}",
                f"  board vm stop {dev_name}",
                "",
                f"Shaped in {total_min}m {total_sec}s",
            ],
        )
    else:
        con.completion_box(
            f"{dev_name}'s board is ready",
            [
                "Admin:",
                f"  board vm start {dev_name}",
                f"  board vm stop {dev_name}",
                "  board shape",
                "",
                f"Shaped in {total_min}m {total_sec}s",
            ],
        )

    con.play_sound()

    webhook_url = os.environ.get("BOARD_WEBHOOK_URL", "")
    if webhook_url:
        con.webhook(
            webhook_url,
            f"Board shaped for {dev_name} ({vm_sku} in {location}) -- {total_min}m {total_sec}s",
        )

    # Warnings
    if provision_warnings:
        con.warn_summary("Warnings", provision_warnings)
        con.info(f"Re-run: board install-projects {dev_name}")

    # Board pass offer
    if not is_self:
        if await prompts.confirm(f"Create a board pass for {dev_name}?"):
            from board.cli.export_pass import _run_export_pass

            await _run_export_pass(
                name=dev_name,
                environment=environment,
                region=location,
                region_short=region_short,
            )
        else:
            con.info(f"Create one later with: board export-pass {dev_name}")


def up_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate inputs without deploying."),
    demo: bool = typer.Option(False, "--demo", help="Use canned data for all external calls."),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Use env vars/defaults, skip prompts.",
    ),
    env: str = typer.Option("", "--env", help="Environment name override."),
    location: str = typer.Option("", "--location", help="Azure region (e.g. australiaeast)."),
    region_short: str = typer.Option("", "--region-short", help="Short region code (e.g. aue)."),
) -> None:
    """Shape a new developer board (5-phase setup wizard)."""
    asyncio.run(_run_up(dry_run, demo, non_interactive, env, location, region_short))
