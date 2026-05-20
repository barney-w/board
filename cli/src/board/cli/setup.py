"""board up — 5-phase setup wizard for provisioning a new developer VM."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import time
from pathlib import Path

import typer

from board.core import config as cfg
from board.core import policies as pol
from board.core import tags as tag_loader
from board.core.errors import BoardError, DeploymentError, PolicyViolationError, SSHError
from board.models.deployment import DeploymentConfig, LlmConfig
from board.ui import console as con
from board.ui import prompts

# ── VM Size catalog ──

VM_SIZE_CATALOG = [
    {"sku": "Standard_D2s_v6", "label": "Standard_D2s_v6  -- 2 vCPU,  8 GB RAM", "cost": "~55"},
    {"sku": "Standard_D4s_v6", "label": "Standard_D4s_v6  -- 4 vCPU, 16 GB RAM", "cost": "~110"},
    {"sku": "Standard_D8s_v6", "label": "Standard_D8s_v6  -- 8 vCPU, 32 GB RAM", "cost": "~220"},
]

# Azure resource group naming: 1-90 chars, alphanumerics / underscore / parens
# / hyphen / period (no trailing period).
RG_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_().-]{1,89}[A-Za-z0-9_()-]$")

TOTAL_STEPS = 5


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


async def _detect_public_ip() -> str:
    """Best-effort detection of the caller's public IP address."""
    import aiohttp

    try:
        async with (
            aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session,
            session.get("https://api.ipify.org") as resp,
        ):
            if resp.status == 200:
                return (await resp.text()).strip()
    except Exception:
        pass
    return ""


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
    non_interactive: bool,
    rg_arg: str,
    preset_path: str,
) -> None:
    """Async implementation of the up command."""
    if non_interactive:
        os.environ["BOARD_NON_INTERACTIVE"] = "1"

    # Load preset (if any) so we can pre-fill the wizard prompts.
    preset: dict[str, str] = {}
    if preset_path:
        try:
            preset = cfg.load_preset(Path(preset_path))
        except FileNotFoundError as exc:
            con.error(str(exc))
            raise typer.Exit(1) from exc
        con.info(f"Preset: {preset_path} ({len(preset)} value(s) loaded)")

    # ══════════════════════════════════════════════════
    # [1/5] Configure
    # ══════════════════════════════════════════════════

    con.ascii_banner("create a new board")
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

    # ── Resource group (required input — must already exist) ──
    rg_default = rg_arg or preset.get("resourceGroup", "")
    if non_interactive:
        if not rg_default:
            con.error(
                "Resource group is required in non-interactive mode. "
                "Pass --rg or set 'resourceGroup' in the preset."
            )
            raise typer.Exit(1)
        rg_name = rg_default
        con.success(f"Resource group: {rg_name}")
    else:
        rg_name = await prompts.input_validated(
            "Resource group (must already exist)",
            default=rg_default,
            pattern=RG_NAME_PATTERN.pattern,
            message="Invalid Azure resource group name (1-90 chars, alphanumerics/_-.()).",
        )

    # Resolve credential + caller principal up front so we can verify the RG.
    credential_for_check: object | None = None
    sub_id_for_check: str | None = None
    if dry_run:
        # Skip the live verify in dry run; trust the inputs.
        location = preset.get("location", "")
        con.success(f"Resource group: {rg_name} (verification skipped in dry run)")
    else:
        from board.azure.auth import get_credential, get_subscription_id
        from board.azure.deployment import verify_resource_group
        from board.azure.mfa import get_signed_in_user_id

        credential_for_check = get_credential()
        try:
            sub_id_for_check = await get_subscription_id()
        except RuntimeError as exc:
            con.error(str(exc))
            con.info("Run: az login")
            raise typer.Exit(1) from exc

        principal_id_for_check = await get_signed_in_user_id() or ""
        with con.spin(f"Verifying access to resource group '{rg_name}'..."):
            try:
                location, _rg_tags = await verify_resource_group(
                    credential_for_check,
                    sub_id_for_check,
                    rg_name,
                    principal_id_for_check,
                )
            except BoardError as exc:
                con.error(str(exc))
                raise typer.Exit(1) from exc
        con.success(f"Resource group: {rg_name} ({location}, Contributor verified)")

    deploy_cfg = DeploymentConfig(
        developer_name=dev_name,
        resource_group=rg_name,
        location=location,
    )
    con.info(f"VM name: {deploy_cfg.vm_name}")

    # Pre-flight: surface any boards already in this RG. Catches the silent
    # duplicate trap where a user re-runs with a slightly different dev name
    # and ends up with two of every per-VM resource.
    if not dry_run and credential_for_check is not None and sub_id_for_check is not None:
        from board.azure.compute import list_vms

        with con.spin(f"Checking for existing boards in '{rg_name}'..."):
            try:
                rg_vms = await list_vms(
                    credential_for_check,
                    sub_id_for_check,
                    rg_name,
                )
            except Exception as exc:  # noqa: BLE001 -- best-effort probe
                con.warn(f"Could not list existing VMs: {exc}")
                rg_vms = []

        existing_boards = [vm for vm in rg_vms if vm.get("tags", {}).get("project") == "devvm"]
        name_conflict = any(vm["name"] == deploy_cfg.vm_name for vm in existing_boards)

        if name_conflict:
            con.error(
                f"A board named '{deploy_cfg.vm_name}' already exists in '{rg_name}'. "
                f"Pick a different developer name, or delete the existing board first "
                f"with: board vm delete {dev_name}"
            )
            raise typer.Exit(1)

        if existing_boards:
            con.info(f"Found {len(existing_boards)} existing board(s) in this RG:")
            for vm in existing_boards:
                owner = vm.get("tags", {}).get("owner", "?")
                size = vm.get("vm_size", "?")
                power = vm.get("power_state", "?")
                con.info(f"  • {vm['name']}  (owner: {owner}, {size}, {power})")
            con.info(f"This run will add a new board: {deploy_cfg.vm_name}")

            if non_interactive:
                con.success("Non-interactive mode: proceeding with new board creation.")
            else:
                action = await prompts.choose(
                    "How do you want to proceed?",
                    [
                        f"Create new board ({deploy_cfg.vm_name})",
                        "Cancel — I'll delete an existing board first",
                    ],
                    default=f"Create new board ({deploy_cfg.vm_name})",
                )
                if "Cancel" in action:
                    con.info("Cancelled. Delete a board with: board vm delete <name>")
                    raise typer.Exit(0)

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
        from board.core.manifest import load_all as load_manifests
        from board.core.manifest import required_keyvault_secrets

        manifests = load_manifests(manifest_dir, filter_names=selected_projects)
        env_kv_secrets, repo_auth_kv_secrets = required_keyvault_secrets(manifests)
        all_kv_secrets = env_kv_secrets | repo_auth_kv_secrets

        if all_kv_secrets and not non_interactive:
            reasons: list[str] = []
            if repo_auth_kv_secrets:
                reasons.append("clone private repos (token in Key Vault)")
            if env_kv_secrets:
                reasons.append("populate runtime env vars from Key Vault")
            reason_text = " and to ".join(reasons)
            kv_choice = await prompts.choose(
                f"These projects need a Key Vault to {reason_text}:",
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
                con.info("Secrets can be added later with: board admin")
                if repo_auth_kv_secrets:
                    con.warn(
                        "Repo clones requiring Key Vault auth will fail until "
                        "a Key Vault is configured."
                    )

    # LLM provider
    llm_config = LlmConfig()

    if selected_projects and not non_interactive:
        # Check if any selected project needs LLM env vars
        has_llm_projects = False
        try:
            for m in manifests:
                if m.env and m.env.keyvault_secrets:
                    for key in m.env.keyvault_secrets:
                        if "ANTHROPIC" in key or "OPENAI" in key:
                            has_llm_projects = True
                            break
        except NameError:
            pass

        if has_llm_projects:
            llm_choice = await prompts.choose(
                "LLM provider for projects:",
                [
                    "Azure AI Foundry (Claude via Azure)",
                    "Anthropic API (direct)",
                    "Skip (configure later)",
                ],
            )

            if "Foundry" in llm_choice:
                foundry_endpoint = await prompts.input_text(
                    "Foundry endpoint URL",
                    default="",
                )
                if not foundry_endpoint:
                    con.warn("No endpoint provided, skipping LLM config")
                else:
                    # Normalise endpoint (strip trailing slash for consistency)
                    foundry_endpoint = foundry_endpoint.rstrip("/")
                    foundry_key = await prompts.secret("Foundry API key")
                    if foundry_key:
                        llm_config = LlmConfig(
                            provider="foundry",
                            api_key=foundry_key,
                            endpoint=foundry_endpoint,
                        )
                        con.success(f"Foundry: {foundry_endpoint}")
                    else:
                        con.warn("No API key provided, skipping LLM config")

            elif "Anthropic" in llm_choice:
                anthropic_key = await prompts.secret("Anthropic API key")
                if anthropic_key:
                    llm_config = LlmConfig(provider="anthropic", api_key=anthropic_key)
                    con.success("Anthropic API: key provided")
                else:
                    con.warn("No API key provided, skipping LLM config")

            else:
                con.info("LLM credentials can be added later with: board admin")

    # Extra tags
    extra_tags: dict[str, str] = {}
    tags_path = tag_loader.find_tags_file()
    apply_extra_tags = False
    if non_interactive:
        if tags_path is not None:
            extra_tags = tag_loader.load_tags(tags_path)
            apply_extra_tags = bool(extra_tags)
            if apply_extra_tags:
                con.success(f"Loaded {len(extra_tags)} tag(s) from {tags_path.name}")
    else:
        apply_extra_tags = await prompts.confirm(
            "Include extra tags? (yes: load all from board.tags.yaml, no: skip)",
            default=True,
        )
        if apply_extra_tags:
            if tags_path is None:
                example = tag_loader.find_example_file()
                con.error(f"{tag_loader.TAGS_FILENAME} not found.")
                if example is not None:
                    con.info(
                        f"Copy {example.name} to {tag_loader.TAGS_FILENAME}, "
                        "fill in your values, then re-run."
                    )
                else:
                    con.info(
                        f"Create {tag_loader.TAGS_FILENAME} at the repo root with a top-level "
                        "'tags:' map, then re-run."
                    )
                raise typer.Abort()
            extra_tags = tag_loader.load_tags(tags_path)
            if not extra_tags:
                con.error(f"{tags_path.name} contains no tags under the top-level 'tags:' key.")
                raise typer.Abort()
            con.success(f"Loaded {len(extra_tags)} tag(s) from {tags_path.name}")
            for k, v in extra_tags.items():
                con.info(f"    {k}: {v}")
        else:
            con.warn("Skipping extra tags -- deploy will fail if Azure Policy requires them")

    # Authentication method
    auth_method = await prompts.choose(
        "Authentication method:",
        [
            "Entra ID (recommended -- no SSH keys, tenant-locked)",
            "SSH key (classic -- generate or bring your own key)",
        ],
        default="Entra ID (recommended -- no SSH keys, tenant-locked)",
    )
    auth_method = "entra-id" if "Entra" in auth_method else "ssh-key"

    # Resolve Entra ID details
    tenant_id = ""
    dev_principal_id = ""

    if auth_method == "entra-id":
        tenant_id_result = subprocess.run(
            ["az", "account", "show", "--query", "tenantId", "-o", "tsv"],
            capture_output=True,
            text=True,
            check=False,
        )
        if tenant_id_result.returncode != 0 or not tenant_id_result.stdout.strip():
            con.error("Could not resolve tenant ID. Ensure you are logged in with 'az login'.")
            raise typer.Abort()
        tenant_id = tenant_id_result.stdout.strip()

        if is_self:
            entra_self = await prompts.confirm(
                "Is this board for yourself (the currently signed-in Azure user)?",
                default=True,
            )
        else:
            entra_self = False

        if entra_self:
            principal_result = subprocess.run(
                ["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"],
                capture_output=True,
                text=True,
                check=False,
            )
            if principal_result.returncode != 0 or not principal_result.stdout.strip():
                con.error("Could not resolve your Entra ID object ID.")
                raise typer.Abort()
            dev_principal_id = principal_result.stdout.strip()
        else:
            dev_email = await prompts.input_text("Developer's email address:")
            if not dev_email:
                raise typer.Abort()
            principal_result = subprocess.run(
                ["az", "ad", "user", "show", "--id", dev_email, "--query", "id", "-o", "tsv"],
                capture_output=True,
                text=True,
                check=False,
            )
            if principal_result.returncode != 0 or not principal_result.stdout.strip():
                con.error(f"Could not find Entra ID user: {dev_email}")
                raise typer.Abort()
            dev_principal_id = principal_result.stdout.strip()

        con.success(f"Entra ID: tenant {tenant_id[:8]}..., principal {dev_principal_id[:8]}...")

    # Security group for VM login RBAC + MFA (Entra ID only).
    security_group_name = ""
    if auth_method == "entra-id":
        from board.azure.mfa import DEFAULT_GROUP_NAME

        sg_policy_default = DEFAULT_GROUP_NAME
        _policies_for_default = pol.load()
        if _policies_for_default is not None:
            sg_policy_default = _policies_for_default.security_group_name

        env_sg = os.environ.get("BOARD_SECURITY_GROUP", "").strip()
        if non_interactive:
            security_group_name = env_sg or sg_policy_default
            con.success(f"Security group: {security_group_name}")
        else:
            con.info("Existing Entra ID group used as-is; created if it doesn't exist.")
            security_group_name = (
                await prompts.input_text(
                    "Security group for VM login",
                    default=env_sg or sg_policy_default,
                )
            ).strip() or sg_policy_default

    # SSH key
    key_path = deploy_cfg.ssh_key_path_expanded
    ssh_pub_key = ""

    if auth_method == "entra-id":
        # Entra ID: silently generate an ephemeral keypair for admin automation only
        if dry_run:
            ssh_pub_key = "dry-run-placeholder"
            con.success("Auth: Entra ID (admin key skipped in dry run)")
        else:
            from board.ssh.keys import generate_keypair

            _, ssh_pub_key = await generate_keypair(key_path)
            con.success("Auth: Entra ID (ephemeral admin key generated)")
    elif non_interactive:
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

    # SSH source IP restriction
    env_ssh_source_ip = os.environ.get("BOARD_SSH_SOURCE_IP", "")
    if non_interactive:
        allowed_ssh_source_ip = env_ssh_source_ip or "*"
        con.success(f"SSH source: {allowed_ssh_source_ip}")
    else:
        detected_ip = ""
        if not env_ssh_source_ip:
            detected_ip = await _detect_public_ip()
        ip_default = env_ssh_source_ip or detected_ip or "*"
        con.info("Restrict SSH access to a source IP/CIDR (e.g. 203.0.113.0/24)")
        con.info("Use * to allow any source (not recommended for production)")
        if detected_ip:
            con.info(f"Detected your public IP: {detected_ip}")
        allowed_ssh_source_ip = await prompts.input_text(
            "Allowed SSH source IP/CIDR",
            default=ip_default,
        )

    # Auto-start schedule
    env_auto_start = os.environ.get("BOARD_AUTO_START", "")
    if non_interactive:
        enable_auto_start = env_auto_start.lower() in ("1", "true", "yes")
    else:
        enable_auto_start = await prompts.confirm(
            "Enable auto-start? (starts VM on weekday mornings)",
            default=False,
        )
    auto_start_time = "0800"
    if enable_auto_start and not non_interactive:
        auto_start_time = await prompts.input_text(
            "Auto-start time (HHmm, local timezone)",
            default="0800",
        )

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
    auth_display = "Entra ID (tenant-locked)" if auth_method == "entra-id" else "SSH key"
    auto_start_display = (
        f"{auto_start_time[:2]}:{auto_start_time[2:]} AEST (weekdays)"
        if enable_auto_start
        else "disabled"
    )
    ssh_source_display = (
        allowed_ssh_source_ip if allowed_ssh_source_ip != "*" else "* (any -- not recommended)"
    )
    summary_lines = [
        f"Developer:     {dev_name}",
        f"Resource group: {deploy_cfg.resource_group}",
        f"VM name:        {deploy_cfg.vm_name}",
        f"Auth:          {auth_display}",
        f"VM Size:       {vm_sku}",
        f"Region:        {location}",
        "OS:            Ubuntu 24.04 LTS",
        "Disk:          128 GB Standard SSD",
        f"SSH source:    {ssh_source_display}",
        "Auto-shutdown: 19:00 AEST (idle-aware, backstop 22:00)",
        f"Auto-start:   {auto_start_display}",
        "",
        "Estimated monthly cost:",
        f"  Compute (with auto-shutdown): {cost_compute}",
        "  Disk + Public IP:             ~$24",
    ]
    if selected_projects:
        summary_lines.append(f"Projects:       {' '.join(selected_projects)}")
    if kv_name:
        summary_lines.append(f"Key Vault:      {kv_name}")
    if llm_config.provider == "foundry":
        summary_lines.append(f"LLM:            Azure AI Foundry ({llm_config.endpoint})")
    elif llm_config.provider == "anthropic":
        summary_lines.append("LLM:            Anthropic API (direct)")

    con.summary_box("Deployment Summary", summary_lines)

    # Policy enforcement
    policies = pol.load()
    if policies is not None:
        con.info("Checking policies (board.policies.yaml)...")
        try:
            warnings = pol.enforce(
                policies,
                vm_sku=vm_sku,
                region=location,
                auth_method=auth_method,
                developer_name=dev_name,
                resource_group=deploy_cfg.resource_group,
            )
            for w in warnings:
                con.warn(w)
            con.success("Policies: all checks passed")
        except PolicyViolationError as exc:
            con.error(str(exc))
            raise typer.Exit(1) from exc

    if not await prompts.confirm("Create this board?"):
        con.info("Cancelled.")
        raise typer.Exit(0)

    # ══════════════════════════════════════════════════
    # [4/5] Provision
    # ══════════════════════════════════════════════════

    con.step(4, TOTAL_STEPS, "Provision")

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
    # The RG was already verified in step 1 — we just deploy into it. Tags on
    # the RG itself are owned by whoever provisioned it, not board.
    phase_start = time.monotonic()
    provision_warnings: list[str] = []

    from board.azure.auth import get_credential, get_subscription_id
    from board.azure.deployment import deploy

    credential = get_credential()
    sub_id = await get_subscription_id()

    # Key Vault creation
    kv_resource_id = ""
    if create_kv and kv_name:
        try:
            from board.azure.auth import get_tenant_id
            from board.azure.keyvault import create_or_recover_vault

            kv_tenant_id = await get_tenant_id()

            with con.spin(f"Creating Key Vault: {kv_name}..."):
                await create_or_recover_vault(
                    credential,
                    sub_id,
                    deploy_cfg.resource_group,
                    kv_name,
                    location,
                    kv_tenant_id,
                )
            kv_resource_id = (
                f"/subscriptions/{sub_id}"
                f"/resourceGroups/{deploy_cfg.resource_group}"
                f"/providers/Microsoft.KeyVault/vaults/{kv_name}"
            )
            con.success(f"Key Vault: {kv_name}")
        except BoardError as exc:
            con.error(f"Key Vault creation failed: {exc}")
            con.info(
                f"Confirm you have 'Contributor' (or equivalent) on resource group "
                f"'{deploy_cfg.resource_group}' and re-run setup."
            )
            raise typer.Exit(1) from exc

    # Auto-populate Key Vault with LLM credentials
    if kv_name and kv_resource_id and llm_config.provider != "none":
        llm_secrets: dict[str, str] = {}
        if llm_config.provider == "foundry" and llm_config.api_key and llm_config.endpoint:
            llm_secrets["anthropic-foundry-api-key"] = llm_config.api_key
            llm_secrets["azure-openai-endpoint"] = llm_config.endpoint
        elif llm_config.provider == "anthropic" and llm_config.api_key:
            llm_secrets["anthropic-api-key"] = llm_config.api_key

        if llm_secrets:
            from board.azure.keyvault import (
                ensure_secrets_officer_role,
                set_secret_with_propagation_retry,
            )
            from board.azure.mfa import get_signed_in_user_id

            runner_id = await get_signed_in_user_id()
            if not runner_id:
                con.error(
                    "Cannot store LLM credentials: failed to resolve the "
                    "currently signed-in Entra ID user. Run 'az login' as a "
                    "user account (not a service principal) and re-run setup."
                )
                raise typer.Exit(1)

            try:
                with con.spin(
                    f"Granting 'Key Vault Secrets Officer' on {kv_name} to current user..."
                ):
                    await ensure_secrets_officer_role(credential, sub_id, kv_resource_id, runner_id)
            except BoardError as exc:
                con.error(str(exc))
                con.info(
                    "Your account needs 'Microsoft.Authorization/roleAssignments/write' "
                    f"on '{kv_name}' (e.g. 'Owner' or 'User Access Administrator' on the "
                    f"resource group). Ask a subscription admin to grant it, or assign "
                    f"yourself 'Key Vault Secrets Officer' on the vault, then re-run setup."
                )
                raise typer.Exit(1) from exc

            vault_url = f"https://{kv_name}.vault.azure.net/"
            with con.spin("Storing LLM credentials in Key Vault..."):
                for secret_name, secret_value in llm_secrets.items():
                    try:
                        await set_secret_with_propagation_retry(
                            vault_url, credential, secret_name, secret_value
                        )
                    except BoardError as exc:
                        con.error(str(exc))
                        raise typer.Exit(1) from exc
                    con.success(f"Key Vault: {secret_name}")

    # ── Resolve security group for VM RBAC (Entra ID only) ──
    rbac_principal_id = dev_principal_id
    rbac_principal_type = "User"
    login_group_id: str | None = None

    if auth_method == "entra-id":
        from board.azure.mfa import ensure_board_group

        with con.spin(f"Resolving security group '{security_group_name}'..."):
            login_group_id, group_msg = await ensure_board_group(security_group_name)

        if login_group_id:
            con.success(group_msg)
            rbac_principal_id = login_group_id
            rbac_principal_type = "Group"
        else:
            con.warn(f"Could not resolve security group: {group_msg}")
            con.warn(f"Falling back to individual user RBAC for {dev_principal_id[:8]}...")

    # ── Shared network (one vnet + subnet per RG) ──
    from board.azure.deployment import ensure_network

    rg_name_for_prefix = deploy_cfg.resource_group
    prefix = rg_name_for_prefix[3:] if rg_name_for_prefix.startswith("rg-") else rg_name_for_prefix
    network_tags: dict[str, str] = {
        "project": "devvm",
        "managed-by": "bicep",
        **extra_tags,
    }
    infra_dir = cfg._find_infra_dir()
    network_bicep = infra_dir / "modules" / "network.bicep"

    try:
        with con.spin(f"Ensuring shared network for '{deploy_cfg.resource_group}'..."):
            _vnet_id, _subnet_id = await ensure_network(
                credential,
                sub_id,
                deploy_cfg.resource_group,
                prefix,
                location,
                network_tags,
                network_bicep,
                allowed_ssh_source_ip=allowed_ssh_source_ip,
            )
        con.success(f"Network: vnet-{prefix} ready (subnet snet-{prefix}, nsg-{prefix})")
    except (BoardError, DeploymentError) as exc:
        con.error(str(exc))
        raise typer.Exit(1) from exc

    # Bicep deployment
    bicep_file = infra_dir / "main.bicep"
    deploy_params = {
        "developerName": dev_name,
        "vmSku": vm_sku,
        "adminSshPublicKey": ssh_pub_key,
        "useEntraIdLogin": auth_method == "entra-id",
        "enableAutoStart": enable_auto_start,
    }
    if policies is not None and policies.auto_shutdown.enabled:
        deploy_params["autoShutdownTime"] = policies.auto_shutdown.time
        deploy_params["backstopShutdownTime"] = policies.auto_shutdown.backstop_time
    if enable_auto_start:
        deploy_params["autoStartTime"] = auto_start_time
    if auth_method == "entra-id":
        deploy_params["entraLoginTenantId"] = tenant_id
        deploy_params["entraLoginPrincipalId"] = rbac_principal_id
        deploy_params["entraLoginPrincipalType"] = rbac_principal_type
    if kv_resource_id:
        deploy_params["keyVaultResourceId"] = kv_resource_id
    if extra_tags:
        deploy_params["extraTags"] = extra_tags

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

    # ── Conditional Access: MFA for VM SSH ──
    if auth_method == "entra-id":
        from board.azure.mfa import add_member_to_board_group, check_mfa_policy

        with con.spin("Checking MFA policy for Azure Linux VM SSH..."):
            mfa_exists, mfa_name = await check_mfa_policy()
        if mfa_exists:
            con.success(f"MFA policy active: {mfa_name}")
        else:
            con.warn("No MFA Conditional Access policy found for Azure Linux VM SSH.")
            con.warn("A tenant admin should run: board admin mfa-setup")
            provision_warnings.append(
                "MFA: No Conditional Access policy. Run 'board admin mfa-setup'."
            )

        # Ensure the developer is in the security group (for both RBAC and MFA).
        if login_group_id and dev_principal_id:
            with con.spin(f"Adding developer to '{security_group_name}'..."):
                added, add_msg = await add_member_to_board_group(login_group_id, dev_principal_id)
            if added:
                con.success(add_msg)
            else:
                con.warn(add_msg)

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
                    llm_config=llm_config,
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
    from board.ssh.config_file import write_managed_block

    ssh_config_path = Path.home() / ".ssh" / "config"

    if auth_method == "entra-id":
        from board.ssh.config_file import build_entra_id_config_block

        block = build_entra_id_config_block(
            alias=deploy_cfg.ssh_host_alias,
            hostname=deploy_cfg.hostname,
        )
    else:
        from board.ssh.config_file import build_ssh_key_config_block

        block = build_ssh_key_config_block(
            alias=deploy_cfg.ssh_host_alias,
            hostname=deploy_cfg.hostname,
            key_path=str(key_path),
        )

    write_managed_block(ssh_config_path, deploy_cfg.ssh_host_alias, block)

    if auth_method == "entra-id":
        from board.ssh.config_file import refresh_entra_certs

        with con.spin("Generating Entra ID certificates..."):
            cert_ok, entra_user = refresh_entra_certs(
                deploy_cfg.ssh_host_alias,
                deploy_cfg.resource_group,
                deploy_cfg.vm_name,
            )
        if cert_ok:
            # Re-write SSH config with the Entra user from the cert
            if entra_user:
                block = build_entra_id_config_block(
                    alias=deploy_cfg.ssh_host_alias,
                    hostname=deploy_cfg.hostname,
                    user=entra_user,
                )
                write_managed_block(ssh_config_path, deploy_cfg.ssh_host_alias, block)
            con.success("SSH config ready (Entra ID certificates generated)")
        else:
            con.warn("SSH config ready (certificate generation failed — run 'az login' and retry)")
    else:
        con.success("SSH config ready")

    # Timing
    total_elapsed = time.monotonic() - phase_start
    total_min = int(total_elapsed) // 60
    total_sec = int(total_elapsed) % 60

    # Completion box
    if auth_method == "entra-id":
        if is_self:
            con.completion_box(
                f"{dev_name}'s board is ready",
                [
                    "Connect in VS Code:",
                    f"  Remote-SSH → {deploy_cfg.ssh_host_alias}",
                    "  Start your app, then open the Ports tab to see the URL.",
                    "",
                    f"Terminal:  ssh {deploy_cfg.ssh_host_alias}",
                    "",
                    "Prerequisite: az login",
                    "Auth: Entra ID (tenant-locked)",
                    "",
                    f"Created in {total_min}m {total_sec}s",
                ],
            )
        else:
            con.completion_box(
                f"{dev_name}'s board is ready",
                [
                    "Admin:",
                    f"  board vm start {dev_name}",
                    f"  board vm stop {dev_name}",
                    "  board admin",
                    "",
                    "Developer connects via VS Code Remote-SSH.",
                    "  Start app → Ports tab shows the browser URL.",
                    "",
                    "Prerequisite: az login",
                    "Auth: Entra ID (tenant-locked)",
                    "",
                    f"Created in {total_min}m {total_sec}s",
                ],
            )
    elif is_self:
        con.completion_box(
            f"{dev_name}'s board is ready",
            [
                "Connect in VS Code:",
                f"  Remote-SSH → {deploy_cfg.ssh_host_alias}",
                "  Start your app, then open the Ports tab to see the URL.",
                "",
                f"Terminal:  ssh {deploy_cfg.ssh_host_alias}",
                "",
                "Daily:",
                f"  board vm start {dev_name}",
                f"  board vm stop {dev_name}",
                "",
                f"Created in {total_min}m {total_sec}s",
            ],
        )
    else:
        con.completion_box(
            f"{dev_name}'s board is ready",
            [
                "Admin:",
                f"  board vm start {dev_name}",
                f"  board vm stop {dev_name}",
                "  board admin",
                "",
                f"Created in {total_min}m {total_sec}s",
            ],
        )

    con.play_sound()

    webhook_url = os.environ.get("BOARD_WEBHOOK_URL", "")
    if webhook_url:
        con.webhook(
            webhook_url,
            f"Board created for {dev_name} ({vm_sku} in {location}) -- {total_min}m {total_sec}s",
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
                resource_group=rg_name,
                region=location,
            )
        else:
            con.info(f"Create one later with: board export-pass {dev_name} --rg {rg_name}")


def up_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate inputs without deploying."),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Use --rg/--preset and skip prompts.",
    ),
    rg: str = typer.Option(
        "",
        "--rg",
        help="Existing Azure resource group to deploy into. Required if no preset supplies one.",
    ),
    preset: str = typer.Option(
        "",
        "--preset",
        help="Path to a .bicepparam preset file with default values for the wizard.",
    ),
) -> None:
    """Create a new developer board (5-phase setup wizard)."""
    asyncio.run(_run_up(dry_run, non_interactive, rg, preset))
