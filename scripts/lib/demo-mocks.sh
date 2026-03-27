#!/usr/bin/env bash
# Demo mode mocks — produces authentic gum-styled output without Azure or SSH.
# Sourced by setup.sh when --demo is passed.
# All external calls (az, ssh, ssh-keygen) are replaced with canned responses.
# All input functions (ui_choose, ui_input, etc.) return pre-defined demo values
# while still rendering styled output via gum.
#
# IMPORTANT: Input mock functions must write display output to STDERR only.
# Only the return value goes to stdout, because callers use $(...) to capture it.

# ── Demo identity (all fictional) ──

_DEMO_DEV_NAME="jbloggs"
_DEMO_ENVIRONMENT="personal"
_DEMO_PERSONA="Another developer"
_DEMO_SUB_NAME="Azure subscription 1"
_DEMO_SUB_ID="00000000-0000-0000-0000-000000000000"
_DEMO_USER_EMAIL="jbloggs@contoso.com"
_DEMO_TENANT="contoso.onmicrosoft.com"
_DEMO_VM_SIZE_LABEL="Standard_D2s_v6  — 2 vCPU,  8 GB RAM  (\$~55/mo)"

# ── Temp directory (must be defined first — used by answer queue below) ──

_DEMO_TMPDIR=$(mktemp -d /tmp/board-demo-XXXXXXXX)
_demo_tmpdir() { echo "$_DEMO_TMPDIR"; }

# Clean up demo temp dir on exit
_demo_cleanup() { rm -rf "$_DEMO_TMPDIR"; }
trap '_demo_cleanup' EXIT

# ── Answer queue for input mocks ──
# Note: ui_choose is called via $(...) which runs in a subshell, so we can't
# use a shell variable for the index — subshell writes are invisible to the parent.
# We use a temp file to persist the counter across subshell boundaries.

_DEMO_CHOOSE_ANSWERS=(
    "$_DEMO_PERSONA"                                    # [1/5] Who is this board for?
    "$_DEMO_ENVIRONMENT"                                # [1/5] Environment
    "$_DEMO_VM_SIZE_LABEL"                              # [1/5] VM size
)

_DEMO_IDX_FILE="${_DEMO_TMPDIR}/.choose-idx"
echo "0" > "$_DEMO_IDX_FILE"

_demo_next_choose_idx() {
    local idx
    idx=$(cat "$_DEMO_IDX_FILE")
    echo $(( idx + 1 )) > "$_DEMO_IDX_FILE"
    echo "$idx"
}

# ── Input function overrides ──
# Display output goes to stderr so $(...) callers only capture the return value.
# Display functions (ui_step, ui_success, ui_summary_box, etc.) are NOT overridden.

ui_choose() {
    local prompt="$1"
    shift
    local idx
    idx=$(_demo_next_choose_idx)
    local answer="${_DEMO_CHOOSE_ANSWERS[$idx]}"
    sleep 0.3
    ui_success "$answer" >&2
    echo "$answer"
}

ui_input() {
    local prompt="$1"
    local default="${2:-}"
    sleep 0.2
    echo "${default:-}"
}

# shellcheck disable=SC2034 # args consumed to match ui_input_validated() signature
ui_input_validated() {
    local prompt="$1"
    sleep 0.3
    echo "$_DEMO_DEV_NAME"
}

ui_confirm() {
    sleep 0.3
    return 0
}

# shellcheck disable=SC2034 # args match ui_checklist() signature
ui_checklist() {
    local prompt="$1"
    shift
    [[ "${1:-}" == --selected=* ]] && shift
    sleep 0.3
    for option in "$@"; do
        [[ "$option" == "None"* ]] && continue
        echo "$option"
    done
}

ui_input_secret() {
    echo ""
}

ui_spin() {
    local title="$1"
    shift
    ui_info "$title" >&2
    sleep 0.5
}

# ── Prerequisite check override ──

check_prerequisites() {
    ui_success "Azure CLI (azure-cli                         2.67.0)"
    ui_success "just (just 1.38.0)"
    ui_success "ssh-keygen (installed)"
    ui_success "ssh (installed)"
    ui_success "gum (gum version v0.14.5)"
    return 0
}

# ── Azure auth override ──

ensure_az_login() {
    ui_success "Logged in as $_DEMO_USER_EMAIL"
    ui_info "Subscription: $_DEMO_SUB_NAME ($_DEMO_SUB_ID)"
    echo ""
    return 0
}

check_existing_vm() {
    echo ""
}

# ── Azure CLI override ──

az() {
    local subcmd="${1:-}"
    case "$subcmd" in
        account)
            shift
            case "${1:-}" in
                show)
                    cat <<'EOF'
{
  "id": "00000000-0000-0000-0000-000000000000",
  "name": "Azure subscription 1",
  "user": { "name": "jbloggs@contoso.com", "type": "user" },
  "tenantId": "00000000-0000-0000-0000-000000000001",
  "state": "Enabled"
}
EOF
                    ;;
                *) echo "" ;;
            esac
            ;;
        rest|vm|group|deployment|role|ad)
            echo ""
            ;;
        *)
            echo ""
            ;;
    esac
    return 0
}

# ── SSH/key overrides ──

ssh-keygen() {
    local args=("$@")
    local key_file=""
    local is_remove=false

    for ((i=0; i<${#args[@]}; i++)); do
        case "${args[$i]}" in
            -R) is_remove=true ;;
            -f) key_file="${args[$((i+1))]:-}" ;;
        esac
    done

    if $is_remove; then
        return 0
    fi

    # Generate a real key pair (KEY_PATH is already redirected to temp dir)
    if [[ -n "$key_file" ]]; then
        mkdir -p "$(command dirname "$key_file")" 2>/dev/null || true
        command ssh-keygen -t ed25519 -C "demo-${_DEMO_DEV_NAME}" -f "$key_file" -N "" -q 2>/dev/null
        return 0
    fi

    return 0
}

ssh() {
    return 0
}

scp() {
    return 0
}

# ── Resource group ──

# shellcheck disable=SC2034 # args match ensure_resource_group() signature
ensure_resource_group() {
    local rg_name="$1" location="$2"
    ui_info "Creating resource group ${rg_name}..."
    sleep 0.5
    ui_success "Resource group ${rg_name} created"
    return 0
}

# ── Deployment ──

# shellcheck disable=SC2034 # args match deploy_vm() signature
deploy_vm() {
    local rg_name="$1" env_name="$2" dev_name="$3" vm_sku="$4"
    local region="${DEFAULT_LOCATION:-australiaeast}"
    local fqdn="devvm-${dev_name}.${region}.cloudapp.azure.com"

    # Simulate deployment progress
    local spinchars='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local states=("Accepted" "Running" "Running" "Succeeded")
    for i in "${!states[@]}"; do
        local char="${spinchars:$((i % ${#spinchars})):1}"
        printf "\r\033[36m  %s Deploying board... %s (%ds)\033[0m" "$char" "${states[$i]}" "$((i * 2 + 1))"
        sleep 0.8
    done
    printf "\r\033[K"

    # Set output variables directly (same as real deploy_vm)
    DEPLOY_VM_NAME="vm-${env_name}-aue-devvm-${dev_name}"
    DEPLOY_PUBLIC_IP="20.53.100.42"
    DEPLOY_FQDN="$fqdn"
    DEPLOY_SSH_CMD="ssh -i ~/.ssh/devvm-${dev_name} devuser@${fqdn}"

    if [[ -n "${DEPLOY_VARS_FILE:-}" ]]; then
        printf 'DEPLOY_VM_NAME=%q\nDEPLOY_PUBLIC_IP=%q\nDEPLOY_FQDN=%q\nDEPLOY_SSH_CMD=%q\n' \
            "$DEPLOY_VM_NAME" "$DEPLOY_PUBLIC_IP" "$DEPLOY_FQDN" "$DEPLOY_SSH_CMD" \
            > "$DEPLOY_VARS_FILE"
    fi

    ui_success "Deployment complete (0m 7s)"
    echo ""
    ui_info "VM Name:    $DEPLOY_VM_NAME"
    ui_info "Public IP:  $DEPLOY_PUBLIC_IP"
    ui_info "FQDN:       $DEPLOY_FQDN"

    return 0
}

# ── Cloud-init ──

wait_for_cloud_init() {
    ui_info "Waiting for VM to accept SSH connections..."
    sleep 1
    ui_success "SSH connection established"
    echo ""
    ui_info "Cloud-init installing tools (Docker, Node.js, Python, dev tools)..."
    sleep 1.5
    ui_success "Cloud-init complete"
    return 0
}

# ── Key Vault ──

create_keyvault() { return 0; }
set_keyvault_secret_interactive() { return 0; }
resolve_keyvault_id() { echo ""; }

# ── Manifest overrides (avoids yq dependency) ──

manifest_list_projects() {
    echo "nextjs-app|Next.js starter app (Node.js/pnpm + Postgres)"
    echo "django-api|Django REST API (Python/uv + Postgres + Redis + Celery)"
}

# shellcheck disable=SC2034 # args match manifest_get() signature
manifest_get() {
    local manifest="$1" query="$2"
    case "$query" in
        '.env.keyvault_secrets // {} | to_entries | .[].value')
            echo ""
            ;;
        *)
            echo ""
            ;;
    esac
}

# ── Sound / webhook suppression ──

ui_play_sound() { true; }
ui_webhook() { true; }
