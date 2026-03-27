#!/usr/bin/env bash
set -euo pipefail

phase_start() { eval "_PHASE_${1}_start=\$SECONDS"; }
phase_end() {
    local name="$1" label="$2"
    local _var_name="_PHASE_${name}_start"
    local start_time="${!_var_name}"
    local elapsed=$(( SECONDS - start_time ))
    local min=$(( elapsed / 60 )) sec=$(( elapsed % 60 ))
    eval "_PHASE_${name}=\"${min}m ${sec}s\""
    ui_success "$label $(printf '%.*s' $((40 - ${#label})) '..............................................') ${min}m ${sec}s"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Argument parsing (early, before sourcing libraries) ──

DRY_RUN=false
DEMO_MODE=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --demo)   DEMO_MODE=true ;;
    esac
done

# Source helper libraries
# shellcheck source=lib/ui.sh
source "${SCRIPT_DIR}/lib/ui.sh"
# shellcheck source=lib/checks.sh
source "${SCRIPT_DIR}/lib/checks.sh"
# shellcheck source=lib/azure.sh
source "${SCRIPT_DIR}/lib/azure.sh"
# shellcheck source=lib/keyvault.sh
source "${SCRIPT_DIR}/lib/keyvault.sh"
# manifest.sh requires yq — in demo mode we override all manifest functions
if ! $DEMO_MODE; then
    # shellcheck source=lib/manifest.sh
    source "${SCRIPT_DIR}/lib/manifest.sh"
fi

# ── Demo mode ──
# When --demo is passed, source mock overrides that replace external calls
# (az, ssh, ssh-keygen) and pre-fill interactive inputs while keeping USE_GUM=true
# for authentic gum-styled output. Used for VHS recordings and demos.

if $DEMO_MODE; then
    # shellcheck source=lib/demo-mocks.sh
    source "${SCRIPT_DIR}/lib/demo-mocks.sh"
fi

# ── Non-interactive mode ──
# When BOARD_NON_INTERACTIVE is set, override ui_* functions to return
# values from env vars or defaults, avoiding any /dev/tty reads or
# interactive prompts. Supported env vars:
#   BOARD_DEV_NAME, BOARD_ENVIRONMENT, BOARD_PROJECTS, BOARD_VM_SKU

if [[ -n "${BOARD_NON_INTERACTIVE:-}" ]]; then
    # shellcheck disable=SC2034 # used by sourced ui.sh
    USE_GUM=false
    # Return the default (second arg) without prompting
    ui_input() { echo "${2:-}"; }
    # Return the default (second arg) if it matches the regex, else fail
    ui_input_validated() { echo "${2:-}"; }
    # Return the first option (second arg, since first is the prompt)
    ui_choose() { echo "$2"; }
    # Always confirm
    ui_confirm() { return 0; }
    # Return BOARD_PROJECTS env var as pre-selected items
    ui_checklist() {
        local IFS=' '
        for proj in ${BOARD_PROJECTS:-}; do
            echo "$proj"
        done
    }
    # Run the command directly without spinner
    ui_spin() { shift; "$@"; }
    # Return empty (skip secrets in non-interactive mode)
    ui_input_secret() { echo ""; }
fi

# Trap Ctrl+C
trap 'echo ""; ui_warn "Cancelled. Clean up partial resources with: just destroy-all"; exit 130' INT

# ── Defaults ──

DEFAULT_LOCATION="australiaeast"
DEFAULT_REGION="aue"
TOTAL_STEPS=5
SELECTED_PROJECTS=""
KV_NAME=""
CREATE_KV=false
PROVISION_WARNINGS=()

# ── VM Size catalog ──

VM_SIZE_SKUS=(   "Standard_D2s_v6"  "Standard_D4s_v6"  "Standard_D8s_v6" )
VM_SIZE_LABELS=( "Standard_D2s_v6  — 2 vCPU,  8 GB RAM"
                 "Standard_D4s_v6  — 4 vCPU, 16 GB RAM"
                 "Standard_D8s_v6  — 8 vCPU, 32 GB RAM" )
VM_SIZE_COSTS=(  "~55"  "~110"  "~220" )

vm_size_options() {
    local i
    for i in "${!VM_SIZE_LABELS[@]}"; do
        local sku="${VM_SIZE_SKUS[$i]}"
        if [[ -n "$AVAILABLE_SKUS" ]]; then
            local sku_line
            sku_line=$(echo "$AVAILABLE_SKUS" | grep "^${sku}	" || true)
            [[ -z "$sku_line" ]] && continue
            if [[ -n "$ZERO_QUOTA_FAMILIES" ]]; then
                local family
                family=$(echo "$sku_line" | cut -f2)
                echo "$ZERO_QUOTA_FAMILIES" | grep -qx "$family" && continue
            fi
        fi
        echo "${VM_SIZE_LABELS[$i]}  (\$${VM_SIZE_COSTS[$i]}/mo)"
    done
    echo "Custom — enter a SKU manually"
}

vm_sku_from_label() {
    local label="$1"
    local i
    for i in "${!VM_SIZE_LABELS[@]}"; do
        if [[ "$label" == "${VM_SIZE_LABELS[$i]}"* ]]; then
            echo "${VM_SIZE_SKUS[$i]}"
            return 0
        fi
    done
    echo "custom"
}

vm_cost_from_sku() {
    local sku="$1"
    local i
    for i in "${!VM_SIZE_SKUS[@]}"; do
        if [[ "$sku" == "${VM_SIZE_SKUS[$i]}" ]]; then
            echo "\$${VM_SIZE_COSTS[$i]}"
            return 0
        fi
    done
    echo "unknown"
}

# ── Welcome ──

ui_ascii_banner "shape a new board"

# ── Prerequisites (silent gate) ──

if ! check_prerequisites; then
    exit 1
fi

# Re-enforce non-interactive mode after prerequisites (check_prerequisites may set USE_GUM=true)
if [[ -n "${BOARD_NON_INTERACTIVE:-}" ]]; then
    # shellcheck disable=SC2034 # used by sourced ui.sh
    USE_GUM=false
fi

# ══════════════════════════════════════════════════
# [1/5] Configure
# ══════════════════════════════════════════════════

ui_step 1 $TOTAL_STEPS "Configure"

# Persona
if [[ -n "${BOARD_NON_INTERACTIVE:-}" ]]; then
    PERSONA="Myself"
else
    PERSONA=$(ui_choose "Who is this board for?" \
        "Myself" \
        "Another developer")
fi

if [[ "$PERSONA" == "Myself" ]]; then
    NAME_PROMPT="Your name"
    IS_SELF=true
else
    NAME_PROMPT="Developer's name"
    IS_SELF=false
fi

echo ""

# Developer name
if [[ -n "${BOARD_NON_INTERACTIVE:-}" && -n "${BOARD_DEV_NAME:-}" ]]; then
    DEV_NAME="$BOARD_DEV_NAME"
    ui_success "Developer: $DEV_NAME"
else
    ui_info "Use initial + last name, lowercase (e.g. jbloggs, asmith, cjones)"
    DEV_NAME=$(ui_input_validated \
        "$NAME_PROMPT" \
        "" \
        '^[a-z][a-z0-9]{0,11}$' \
        "Must be lowercase, start with a letter, alphanumeric only, max 12 chars")
fi

echo ""

# Environment
ENV_OPTIONS=()
for f in "${SCRIPT_DIR}/../infra/config/"*.bicepparam; do
    env_name=$(basename "$f" .bicepparam)
    ENV_OPTIONS+=("$env_name")
done

if [[ -n "${BOARD_NON_INTERACTIVE:-}" && -n "${BOARD_ENVIRONMENT:-}" ]]; then
    ENVIRONMENT="$BOARD_ENVIRONMENT"
    ui_success "Environment: $ENVIRONMENT"
elif (( ${#ENV_OPTIONS[@]} == 1 )); then
    ENVIRONMENT="${ENV_OPTIONS[0]}"
    ui_info "Environment: $ENVIRONMENT"
else
    ENVIRONMENT=$(ui_choose "Environment:" "${ENV_OPTIONS[@]}")
fi

echo ""

# Derived names
RG_NAME="rg-${ENVIRONMENT}-${DEFAULT_REGION}-devvm"
VM_NAME="vm-${ENVIRONMENT}-${DEFAULT_REGION}-devvm-${DEV_NAME}"
FQDN="devvm-${DEV_NAME}.${DEFAULT_LOCATION}.cloudapp.azure.com"

# Project selection
MANIFEST_DIR="${SCRIPT_DIR}/../projects"

if [[ -n "${BOARD_NON_INTERACTIVE:-}" && -n "${BOARD_PROJECTS:-}" ]]; then
    SELECTED_PROJECTS="$BOARD_PROJECTS"
    ui_success "Projects: $SELECTED_PROJECTS"
elif ls "${MANIFEST_DIR}"/*.project.yaml &>/dev/null 2>&1; then
    PROJECT_OPTIONS=()
    while IFS='|' read -r pname pdesc; do
        PROJECT_OPTIONS+=("$pname -- $pdesc")
    done < <(manifest_list_projects "$MANIFEST_DIR")
    PROJECT_OPTIONS+=("None -- empty ~/projects")

    # Pre-select all projects (except "None") by default
    DEFAULT_SELECTED=""
    for opt in "${PROJECT_OPTIONS[@]}"; do
        [[ "$opt" == "None"* ]] && continue
        DEFAULT_SELECTED="${DEFAULT_SELECTED:+$DEFAULT_SELECTED,}$opt"
    done

    SELECTED=$(ui_checklist "Projects to install:" --selected="$DEFAULT_SELECTED" "${PROJECT_OPTIONS[@]}")

    while IFS= read -r line; do
        [[ -z "$line" || "$line" == "None"* ]] && continue
        proj_name="${line%% --*}"
        SELECTED_PROJECTS="${SELECTED_PROJECTS:+$SELECTED_PROJECTS }$proj_name"
    done <<< "$SELECTED"

    if [[ -n "$SELECTED_PROJECTS" ]]; then
        ui_success "Projects: $SELECTED_PROJECTS"
    else
        ui_info "No projects selected"
    fi
fi

# Key Vault
if [[ -n "$SELECTED_PROJECTS" ]]; then
    ALL_KV_SECRETS=""
    for proj in $SELECTED_PROJECTS; do
        manifest="${MANIFEST_DIR}/${proj}.project.yaml"
        if [[ -f "$manifest" ]]; then
            proj_secrets=$(manifest_get "$manifest" '.env.keyvault_secrets // {} | to_entries | .[].value' 2>/dev/null || true)
            ALL_KV_SECRETS="${ALL_KV_SECRETS:+$ALL_KV_SECRETS }$proj_secrets"
        fi
    done
    ALL_KV_SECRETS=$(echo "$ALL_KV_SECRETS" | tr ' ' '\n' | sort -u | tr '\n' ' ' | xargs)

    if [[ -n "$ALL_KV_SECRETS" ]] && [[ -z "${BOARD_NON_INTERACTIVE:-}" ]]; then
        echo ""
        KV_CHOICE=$(ui_choose "These projects use secrets from Key Vault:" \
            "Use existing Key Vault" \
            "Create new Key Vault" \
            "Skip for now")

        case "$KV_CHOICE" in
            *"existing"*)
                KV_NAME=$(ui_input "Key Vault name")
                ;;
            *"Create"*)
                KV_NAME=$(ui_input "Name for new Key Vault" "kv-devvm-${DEV_NAME}")
                CREATE_KV=true
                ;;
            *"Skip"*)
                KV_NAME=""
                ui_info "Secrets can be added later with: just shape"
                ;;
        esac
    fi
fi

echo ""

# SSH key
if $DEMO_MODE; then
    KEY_PATH="$(_demo_tmpdir)/devvm-${DEV_NAME}"
else
    KEY_PATH="$HOME/.ssh/devvm-${DEV_NAME}"
fi

if [[ -n "${BOARD_NON_INTERACTIVE:-}" ]]; then
    # Non-interactive: use existing key or generate one
    if [[ -f "$KEY_PATH" ]]; then
        SSH_PUB_KEY=$(cat "${KEY_PATH}.pub")
        ui_success "Using existing SSH key: $KEY_PATH"
    elif ! $DRY_RUN; then
        ssh-keygen -t ed25519 -C "devvm-${DEV_NAME}" -f "$KEY_PATH" -N "" -q
        SSH_PUB_KEY=$(cat "${KEY_PATH}.pub")
        ui_success "Key generated: $KEY_PATH"
    else
        SSH_PUB_KEY="dry-run-placeholder"
        ui_success "SSH key: would generate $KEY_PATH"
    fi
else
    if [[ -f "$KEY_PATH" ]]; then
        ui_success "Found SSH key: $KEY_PATH"
        echo ""
        KEY_ACTION=$(ui_choose "SSH key:" \
            "Use existing key" \
            "Generate a new key (overwrites existing)" \
            "Use a different key file")
    else
        KEY_ACTION="generate"
    fi

    case "$KEY_ACTION" in
        *"Generate"*|"generate")
            ssh-keygen -t ed25519 -C "devvm-${DEV_NAME}" -f "$KEY_PATH" -N "" -q
            SSH_PUB_KEY=$(cat "${KEY_PATH}.pub")
            ui_success "Key generated: $KEY_PATH"
            ;;
        *"Use existing"*)
            SSH_PUB_KEY=$(cat "${KEY_PATH}.pub")
            ui_success "Using existing key"
            ;;
        *"different"*)
            CUSTOM_KEY=$(ui_input "Path to public key file" "$HOME/.ssh/id_ed25519.pub")
            if [[ ! -f "$CUSTOM_KEY" ]]; then
                ui_error "File not found: $CUSTOM_KEY"
                exit 1
            fi
            SSH_PUB_KEY=$(cat "$CUSTOM_KEY")
            KEY_PATH="${CUSTOM_KEY%.pub}"
            ui_success "Using key: $CUSTOM_KEY"
            ;;
    esac
fi

echo ""

# VM size
if [[ -n "${BOARD_NON_INTERACTIVE:-}" ]]; then
    VM_SKU="${BOARD_VM_SKU:-Standard_D2s_v6}"
    ui_success "VM size: $VM_SKU"
else
    AVAILABLE_SKUS=""
    ZERO_QUOTA_FAMILIES=""
    # Build a JMESPath filter for our catalog SKUs: name=='X' || name=='Y' || ...
    _sku_filter=""
    for _s in "${VM_SIZE_SKUS[@]}"; do
        _sku_filter="${_sku_filter:+${_sku_filter} || }name=='${_s}'"
    done
    _SUB_ID=$(az account show --query id -o tsv 2>/dev/null)
    ui_spin "Checking VM sizes in ${DEFAULT_LOCATION}" \
        bash -c "
            timeout 30 az rest --method get \
                --url \"https://management.azure.com/subscriptions/${_SUB_ID}/providers/Microsoft.Compute/skus?api-version=2021-07-01&\\\$filter=location eq '${DEFAULT_LOCATION}'\" \
                --query \"value[?resourceType=='virtualMachines' && (${_sku_filter}) && length(restrictions)==\\\`0\\\`].{name:name,family:family}\" \
                -o tsv 2>/dev/null > /tmp/az-sku-list &
            timeout 15 az vm list-usage --location $DEFAULT_LOCATION \
                --query \"[?limit=='0'].name.value\" -o tsv \
                2>/dev/null > /tmp/az-zero-quota &
            wait
        "
    AVAILABLE_SKUS=$(cat /tmp/az-sku-list 2>/dev/null) && rm -f /tmp/az-sku-list
    ZERO_QUOTA_FAMILIES=$(cat /tmp/az-zero-quota 2>/dev/null) && rm -f /tmp/az-zero-quota

    SIZE_MENU=()
    while IFS= read -r line; do
        SIZE_MENU+=("$line")
    done < <(vm_size_options)

    if (( ${#SIZE_MENU[@]} == 1 )); then
        ui_error "No VM sizes available in ${DEFAULT_LOCATION}"
        ui_info "Request quota: https://portal.azure.com/#view/Microsoft_Azure_Capacity/QuotaMenuBlade/~/myQuotas"
        echo ""
    fi

    VM_SIZE_LABEL=$(ui_choose "VM size:" "${SIZE_MENU[@]}")
    VM_SKU=$(vm_sku_from_label "$VM_SIZE_LABEL")

    if [[ "$VM_SKU" == "custom" ]]; then
        VM_SKU=$(ui_input "Enter Azure VM SKU" "Standard_D2s_v6")
    fi
fi

echo ""

# ══════════════════════════════════════════════════
# [2/5] Authenticate
# ══════════════════════════════════════════════════

ui_step 2 $TOTAL_STEPS "Authenticate"

if $DRY_RUN; then
    ui_success "Skipping authentication (dry run)"
else
    if ! ensure_az_login; then
        exit 1
    fi

    # Check if VM already exists (needs auth)
    if existing=$(check_existing_vm "$RG_NAME" "$VM_NAME" 2>/dev/null) && [[ -n "$existing" ]]; then
        ui_warn "VM $VM_NAME already exists"
        echo ""
        ACTION=$(ui_choose "What would you like to do?" \
            "Redeploy (update the existing VM)" \
            "Cancel")
        if [[ "$ACTION" == *"Cancel"* ]]; then
            ui_info "Cancelled."
            exit 0
        fi
    fi
fi

echo ""

# ══════════════════════════════════════════════════
# [3/5] Review
# ══════════════════════════════════════════════════

ui_step 3 $TOTAL_STEPS "Review"

COST_COMPUTE=$(vm_cost_from_sku "$VM_SKU")

ui_summary_box "Deployment Summary" \
    "Developer:     $DEV_NAME" \
    "Environment:   $ENVIRONMENT" \
    "VM Size:       $VM_SKU" \
    "Region:        $DEFAULT_LOCATION" \
    "OS:            Ubuntu 24.04 LTS" \
    "Disk:          128 GB Standard SSD" \
    "Auto-shutdown: 19:00 AEST" \
    "" \
    "Estimated monthly cost:" \
    "  Compute (with auto-shutdown): $COST_COMPUTE" \
    "  Disk + Public IP:             ~\$24" \
    "" \
    "Resource group: $RG_NAME" \
    "VM name:        $VM_NAME"

if ! ui_confirm "Shape this board?"; then
    ui_info "Cancelled."
    exit 0
fi

echo ""

# ══════════════════════════════════════════════════
# [4/5] Shape
# ══════════════════════════════════════════════════

ui_step 4 $TOTAL_STEPS "Shape"

# ── Dry-run exit ──
if $DRY_RUN; then
    ui_success "[DRY RUN] Would create resource group: $RG_NAME"
    ui_success "[DRY RUN] Would deploy VM: $VM_NAME ($VM_SKU)"
    ui_success "[DRY RUN] Location: $DEFAULT_LOCATION"
    if [[ -n "$KV_NAME" ]]; then
        ui_success "[DRY RUN] Key Vault: $KV_NAME"
    fi
    if [[ -n "$SELECTED_PROJECTS" ]]; then
        ui_success "[DRY RUN] Projects: $SELECTED_PROJECTS"
    fi
    echo ""
    ui_success "[DRY RUN] Validation complete — all inputs valid"
    exit 0
fi

# ── Cleanup trap for partial failures ──
_CLEANUP_FILES=()
cleanup_on_exit() {
    for f in "${_CLEANUP_FILES[@]}"; do
        rm -f "$f" 2>/dev/null
    done
}
trap cleanup_on_exit EXIT

# ── Clear stale SSH host keys (handles redeploy with new VM host key) ──
ssh-keygen -R "$FQDN" &>/dev/null || true

# ── Infrastructure ──

if ! ensure_resource_group "$RG_NAME" "$DEFAULT_LOCATION" "$ENVIRONMENT"; then
    exit 1
fi

if [[ "$CREATE_KV" == "true" ]]; then
    create_keyvault "$KV_NAME" "$RG_NAME" "$DEFAULT_LOCATION"
    echo ""
    ui_info "Enter secrets for selected projects (press Enter to skip):"
    echo ""
    for secret in $ALL_KV_SECRETS; do
        set_keyvault_secret_interactive "$KV_NAME" "$secret"
    done
    echo ""
fi

KV_RESOURCE_ID=""
if [[ -n "$KV_NAME" ]]; then
    KV_RESOURCE_ID=$(resolve_keyvault_id "$KV_NAME" 2>/dev/null || echo "")
    if [[ -z "$KV_RESOURCE_ID" ]]; then
        ui_warn "Key Vault '$KV_NAME' not found. Skipping KV role assignment."
    fi
fi

phase_start deploy

DEPLOY_VARS_FILE=$(mktemp)
_CLEANUP_FILES+=("$DEPLOY_VARS_FILE")
export DEPLOY_VARS_FILE

ui_info "Deploying board (Bicep deployment — typically 3-8 minutes)..."
echo ""

# Run deploy with visible output — gum spin hides everything for too long
if ! deploy_vm "$RG_NAME" "$ENVIRONMENT" "$DEV_NAME" "$VM_SKU" "$SSH_PUB_KEY" "$SCRIPT_DIR" "$KV_RESOURCE_ID"; then
    rm -f "$DEPLOY_VARS_FILE"
    exit 1
fi
rm -f "$DEPLOY_VARS_FILE"

phase_end deploy "Infrastructure deployed"

echo ""

# ── Cloud-init (tools) ──

phase_start cloudinit

CLOUD_INIT_OK=true
if ! wait_for_cloud_init "$FQDN" "$KEY_PATH" "devuser" "${DEPLOY_PUBLIC_IP:-}"; then
    CLOUD_INIT_OK=false
    ui_warn "Cloud-init did not complete — project provisioning will be skipped"
    ui_info "After cloud-init finishes, run: just install-projects $DEV_NAME"
    PROVISION_WARNINGS+=("Cloud-init did not complete — projects not installed")
fi

phase_end cloudinit "Tools installed"

echo ""

# ── Project provisioning ──

if [[ -n "$SELECTED_PROJECTS" ]] && $CLOUD_INIT_OK; then
    phase_start provision

    if $DEMO_MODE; then
        ui_info "Provisioning projects..."
        sleep 1
        for proj in $SELECTED_PROJECTS; do
            ui_success "${proj}: cloned, dependencies installed"
            sleep 0.3
        done
    else
        PROVISION_LOG=$(mktemp /tmp/board-provision-XXXXXXXX)
        _CLEANUP_FILES+=("$PROVISION_LOG")
        export BOARD_PROVISION_LOG="$PROVISION_LOG"
        export BOARD_PROJECTS="$SELECTED_PROJECTS"
        export DEVVM_PROJECTS="$SELECTED_PROJECTS"

        # Run provisioning with visible output — avoid gum spin hiding long operations
        ui_info "Provisioning projects..."
        echo ""
        bash "${SCRIPT_DIR}/provision-projects.sh" "$FQDN" "$KEY_PATH" "devuser" "$KV_NAME" "${SCRIPT_DIR}/../projects/" 2>>"$PROVISION_LOG" || {
            PROVISION_WARNINGS+=("Some projects had issues")
        }
    fi

    phase_end provision "Projects provisioned"
fi

echo ""

# ── VS Code Tunnel setup (optional) ──

VSCODE_CLI_AVAILABLE=false
if $DEMO_MODE; then
    ui_info "VS Code Tunnel: available after deployment"
    echo ""
elif [[ -n "${BOARD_NON_INTERACTIVE:-}" ]]; then
    # Tunnel setup requires interactive GitHub device code auth — skip in non-interactive mode
    ui_info "Skipping VS Code Tunnel (non-interactive mode). Set up later with: just tunnel-setup ${DEV_NAME}"
    echo ""
else
    # Check if VS Code CLI is actually installed on the VM before offering tunnel setup
    if ssh -i "$KEY_PATH" -o ConnectTimeout=5 -o BatchMode=yes "devuser@${FQDN}" \
        "test -x /usr/local/bin/code" 2>/dev/null; then
        VSCODE_CLI_AVAILABLE=true
    fi

    if $VSCODE_CLI_AVAILABLE && ui_confirm "Set up VS Code Tunnel for browser access?" "yes"; then
    phase_start tunnel

    TUNNEL_NAME="devvm-${DEV_NAME}"
    TUNNEL_URL="https://vscode.dev/tunnel/${TUNNEL_NAME}"

    echo ""
    ui_info "VS Code Tunnel requires GitHub authentication."
    ui_info "The VM will display a code — enter it at the URL shown."
    echo ""

    # Interactive auth — the user needs to complete the device code flow
    # We run this in the foreground so the user can see the device code
    ssh -t -i "$KEY_PATH" "devuser@${FQDN}" \
        "/usr/local/bin/code tunnel user login --provider github" \
        && TUNNEL_AUTH_EXIT=0 || TUNNEL_AUTH_EXIT=$?
    if [[ $TUNNEL_AUTH_EXIT -eq 0 ]]; then
        # Ensure the VM hostname matches the tunnel name so the tunnel registers correctly.
        # Cloud-init sets this on first boot, but we enforce it here for existing VMs and re-runs.
        ssh -i "$KEY_PATH" "devuser@${FQDN}" \
            "sudo hostnamectl set-hostname '${TUNNEL_NAME}'" 2>/dev/null || true

        # Uninstall any existing tunnel service before reinstalling (handles re-runs cleanly)
        ssh -i "$KEY_PATH" "devuser@${FQDN}" \
            "/usr/local/bin/code tunnel service uninstall 2>/dev/null; true" 2>/dev/null

        # Install as a systemd service (tunnel uses OS hostname as its name)
        ssh -i "$KEY_PATH" "devuser@${FQDN}" \
            "/usr/local/bin/code tunnel service install --accept-server-license-terms" 2>/dev/null

        # Verify the tunnel is actually running
        if ssh -i "$KEY_PATH" "devuser@${FQDN}" \
            "systemctl --user is-active code-tunnel.service" 2>/dev/null | grep -q "active"; then
            # Persist tunnel URL for MOTD and board-pass export
            ssh -i "$KEY_PATH" "devuser@${FQDN}" \
                "echo '${TUNNEL_URL}' > ~/.board/tunnel-url"

            phase_end tunnel "VS Code Tunnel ready"
            ui_success "Tunnel URL: ${TUNNEL_URL}"
        else
            ui_warn "Tunnel service not running — check logs with: just ssh ${DEV_NAME} journalctl --user -u code-tunnel"
            PROVISION_WARNINGS+=("VS Code Tunnel service may not be running")
        fi
    else
        ui_warn "Tunnel auth failed — skip for now. Set up later with: just tunnel-setup ${DEV_NAME}"
        PROVISION_WARNINGS+=("VS Code Tunnel not configured")
    fi

    echo ""
    elif ! $VSCODE_CLI_AVAILABLE; then
        ui_warn "VS Code CLI not installed on VM — tunnel setup skipped"
        ui_info "Install later with: just tunnel-setup ${DEV_NAME}"
        PROVISION_WARNINGS+=("VS Code Tunnel not configured (CLI not installed)")
        echo ""
    fi
fi

# ══════════════════════════════════════════════════
# [5/5] Handoff
# ══════════════════════════════════════════════════

ui_step 5 $TOTAL_STEPS "Handoff"

# ── SSH config (auto-add, uses managed markers compatible with justfile & extension) ──

SSH_HOST_ALIAS="devvm-${DEV_NAME}"
MARKER_BEGIN="# BEGIN board: ${SSH_HOST_ALIAS}"
MARKER_END="# END board: ${SSH_HOST_ALIAS}"
SSH_CONFIG_BLOCK="${MARKER_BEGIN}
Host ${SSH_HOST_ALIAS}
    HostName ${FQDN}
    User devuser
    IdentityFile ${KEY_PATH}
    ForwardAgent yes
    ServerAliveInterval 60
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new
${MARKER_END}"

if $DEMO_MODE; then
    SSH_CONFIG_FILE="$(_demo_tmpdir)/ssh-config"
else
    SSH_CONFIG_FILE="$HOME/.ssh/config"
fi
mkdir -p "$(dirname "$SSH_CONFIG_FILE")"
touch "$SSH_CONFIG_FILE"
chmod 600 "$SSH_CONFIG_FILE"

# Remove any existing entry — stale unmarked blocks (from older versions) or marked blocks
if grep -q "Host ${SSH_HOST_ALIAS}$" "$SSH_CONFIG_FILE" 2>/dev/null; then
    awk -v alias="Host ${SSH_HOST_ALIAS}" '
        $0 == alias { skip=1; next }
        /^Host / || /^# (BEGIN|END) board:/ { skip=0 }
        !skip
    ' "$SSH_CONFIG_FILE" > "${SSH_CONFIG_FILE}.tmp" && mv "${SSH_CONFIG_FILE}.tmp" "$SSH_CONFIG_FILE"
fi
if grep -q "$MARKER_BEGIN$" "$SSH_CONFIG_FILE" 2>/dev/null; then
    sed -i.bak "/${MARKER_BEGIN}$/,/${MARKER_END}$/d" "$SSH_CONFIG_FILE"
    rm -f "${SSH_CONFIG_FILE}.bak"
fi

printf '\n%s\n' "$SSH_CONFIG_BLOCK" >> "$SSH_CONFIG_FILE"
ui_success "SSH config ready"

# ── Timing ──

if $DEMO_MODE; then SECONDS=522; fi  # 8m 42s for realistic display
TOTAL_ELAPSED=$(( SECONDS ))
TOTAL_MIN=$(( TOTAL_ELAPSED / 60 ))
TOTAL_SEC=$(( TOTAL_ELAPSED % 60 ))

# ── Completion box ──

if $IS_SELF; then
    ui_completion_box "${DEV_NAME}'s board is ready" \
        "Connect:  ssh ${SSH_HOST_ALIAS}" \
        "VS Code:  Remote-SSH > ${SSH_HOST_ALIAS}" \
        "" \
        "Daily:" \
        "  just start ${DEV_NAME}" \
        "  just stop ${DEV_NAME}" \
        "" \
        "Shaped in ${TOTAL_MIN}m ${TOTAL_SEC}s"
else
    ui_completion_box "${DEV_NAME}'s board is ready" \
        "Admin:" \
        "  just start ${DEV_NAME}" \
        "  just stop ${DEV_NAME}" \
        "  just shape" \
        "" \
        "Shaped in ${TOTAL_MIN}m ${TOTAL_SEC}s"
fi

ui_play_sound
ui_webhook "Board shaped for ${DEV_NAME} (${VM_SKU} in ${DEFAULT_LOCATION}) -- ${TOTAL_MIN}m ${TOTAL_SEC}s"

# ── Warnings (if any) ──

if (( ${#PROVISION_WARNINGS[@]} > 0 )); then
    ui_warn_summary "Warnings" "${PROVISION_WARNINGS[@]}"
    if [[ -n "${PROVISION_LOG:-}" && -s "${PROVISION_LOG:-}" ]]; then
        # Show error/warning lines from the log so users can diagnose without opening the file
        LOG_ERRORS=$(grep -i 'ERR:\|FAIL\|fatal\|error' "$PROVISION_LOG" 2>/dev/null | head -10)
        if [[ -n "$LOG_ERRORS" ]]; then
            ui_info "Log highlights:"
            while IFS= read -r line; do
                ui_info "  $line"
            done <<< "$LOG_ERRORS"
        fi
        ui_info "Full log: $PROVISION_LOG"
    fi
    ui_info "Re-run: just install-projects ${DEV_NAME}"
    echo ""
fi

# ── Board pass or connect ──

if ! $IS_SELF; then
    echo ""
    if ui_confirm "Create a board pass for ${DEV_NAME}?" "yes"; then
        echo ""
        if $DEMO_MODE; then
            local_issued=$(date -u +%Y-%m-%dT%H:%M:%SZ)
            local_expiry=$(date -u -v+30d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
                || date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
                || echo "2026-04-28T00:00:00Z")
            ui_boarding_pass "$DEV_NAME" "$DEFAULT_LOCATION" "$DEFAULT_REGION" \
                "$ENVIRONMENT" "$FQDN" "ssh-key" \
                "$local_issued" "$local_expiry" "${DEV_NAME}-board.zip"
            ui_success "Board pass created: ${DEV_NAME}-board.zip"
            echo ""
            ui_info "Send ${DEV_NAME}-board.zip to ${DEV_NAME}."
            ui_info "Share the passphrase separately (different channel)."
        else
            bash "${SCRIPT_DIR}/export-bundle.sh" "$DEV_NAME" "$ENVIRONMENT" "$DEFAULT_LOCATION" "$DEFAULT_REGION" || {
                ui_warn "Board pass creation failed. Create one later with: just export-pass ${DEV_NAME}"
            }
        fi
    else
        ui_info "Create one later with: just export-pass ${DEV_NAME}"
    fi
else
    echo ""
    if $DEMO_MODE; then
        ui_info "Run: ssh devvm-${DEV_NAME}"
    elif ui_confirm "Connect now?" "yes"; then
        echo ""
        exec ssh -i "$KEY_PATH" "devuser@${FQDN}"
    fi
fi
