#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ui.sh
source "${SCRIPT_DIR}/lib/ui.sh"
# shellcheck source=lib/checks.sh
source "${SCRIPT_DIR}/lib/checks.sh"
# shellcheck source=lib/azure.sh
source "${SCRIPT_DIR}/lib/azure.sh"
# shellcheck source=lib/keyvault.sh
source "${SCRIPT_DIR}/lib/keyvault.sh"
# shellcheck source=lib/manifest.sh
source "${SCRIPT_DIR}/lib/manifest.sh"

DEFAULT_LOCATION="australiaeast"
DEFAULT_REGION="aue"

# Trap Ctrl+C
trap 'echo ""; ui_warn "Board control cancelled."; exit 130' INT

# ── Helper: select environment ──

_select_env() {
    local configs=()
    local env_names=()
    for f in "${SCRIPT_DIR}/../infra/config/"*.bicepparam; do
        [[ -f "$f" ]] || continue
        local base
        base=$(basename "$f" .bicepparam)
        configs+=("$f")
        env_names+=("$base")
    done

    if (( ${#env_names[@]} == 0 )); then
        ui_error "No environments found in infra/config/"
        return 1
    fi

    if (( ${#env_names[@]} == 1 )); then
        ui_info "Auto-selected environment: ${env_names[0]}"
        ENV="${env_names[0]}"
        return 0
    fi

    ENV=$(ui_choose "Select environment:" "${env_names[@]}")
}

# ── Helper: select VM ──

_select_vm() {
    local env_name="$1"
    RG_NAME="rg-${env_name}-${DEFAULT_REGION}-devvm"

    local vm_list
    vm_list=$(az vm list --resource-group "$RG_NAME" --show-details \
        --query '[].{name:name, status:powerState, ip:publicIps, size:hardwareProfile.vmSize}' \
        -o tsv 2>/dev/null) || true

    if [[ -z "$vm_list" ]]; then
        ui_info "No VMs found in resource group $RG_NAME"
        return 1
    fi

    local vm_names=()
    local vm_display=()
    while IFS=$'\t' read -r ip name size status; do
        vm_names+=("$name")
        vm_display+=("$name  ($status, $size, $ip)")
    done <<< "$vm_list"

    if (( ${#vm_names[@]} == 1 )); then
        VM_NAME="${vm_names[0]}"
        ui_info "Auto-selected VM: ${vm_display[0]}"
        return 0
    fi

    local chosen
    chosen=$(ui_choose "Select a VM:" "${vm_display[@]}")

    # Extract VM name from display string (everything before the first space)
    VM_NAME="${chosen%%  *}"
}

# ── Helper: derive VM info from name ──

_derive_vm_info() {
    local vm_name="$1"
    # VM name pattern: vm-<env>-<region>-devvm-<name>
    DEV_NAME="${vm_name##*-}"
    FQDN="devvm-${DEV_NAME}.${DEFAULT_LOCATION}.cloudapp.azure.com"
    KEY_PATH="$HOME/.ssh/devvm-${DEV_NAME}"
}

# ── Manage VMs ──

admin_manage_vms() {
    _select_env || return 0
    _select_vm "$ENV" || return 0
    _derive_vm_info "$VM_NAME"

    while true; do
        echo ""
        ui_summary_box "VM: $VM_NAME" \
            "Developer: $DEV_NAME" \
            "FQDN:      $FQDN" \
            "Key:       $KEY_PATH"

        local vm_action
        vm_action=$(ui_choose "VM action:" \
            "Start" \
            "Stop (deallocate)" \
            "SSH into VM" \
            "Delete VM" \
            "Back")

        case "$vm_action" in
            *"Start"*)
                ui_info "Starting $VM_NAME..."
                az vm start --resource-group "$RG_NAME" --name "$VM_NAME" --no-wait
                ui_success "Start command issued (--no-wait)"
                ;;
            *"Stop"*)
                ui_info "Deallocating $VM_NAME..."
                az vm deallocate --resource-group "$RG_NAME" --name "$VM_NAME" --no-wait
                ui_success "Deallocate command issued (--no-wait)"
                ;;
            *"SSH"*)
                ui_info "Connecting to $FQDN..."
                exec ssh -i "$KEY_PATH" devuser@"$FQDN"
                ;;
            *"Delete"*)
                echo ""
                ui_warn "This will permanently delete VM $VM_NAME and its associated resources."
                if ui_confirm "Are you sure you want to delete $VM_NAME?" "no"; then
                    ui_info "Deleting $VM_NAME..."
                    az vm delete --resource-group "$RG_NAME" --name "$VM_NAME" --force-deletion true --yes
                    ui_success "VM $VM_NAME deleted"
                    return
                else
                    ui_info "Delete cancelled"
                fi
                ;;
            *"Back"*)
                return
                ;;
        esac
    done
}

# ── Provision projects on an existing VM ──

admin_provision_projects() {
    _select_env || return 0
    _select_vm "$ENV" || return 0
    _derive_vm_info "$VM_NAME"

    local manifest_dir="${SCRIPT_DIR}/../projects"

    # Show project checklist
    local project_list
    project_list=$(manifest_list_projects "$manifest_dir")

    if [[ -z "$project_list" ]]; then
        ui_error "No project manifests found in ${manifest_dir}"
        return
    fi

    echo ""
    ui_info "Available projects:"
    while IFS='|' read -r name desc; do
        ui_info "  $name — $desc"
    done <<< "$project_list"
    echo ""

    # Collect project names for checklist
    local project_names=()
    while IFS='|' read -r name desc; do
        project_names+=("$name")
    done <<< "$project_list"

    local selected
    selected=$(ui_checklist "Select projects to provision:" "${project_names[@]}")

    if [[ -z "$selected" ]]; then
        ui_warn "No projects selected"
        return
    fi

    # Build BOARD_PROJECTS space-separated string
    local projects_str=""
    while IFS= read -r proj; do
        [[ -z "$proj" ]] && continue
        if [[ -n "$projects_str" ]]; then
            projects_str="${projects_str} ${proj}"
        else
            projects_str="$proj"
        fi
    done <<< "$selected"

    # Prompt for optional Key Vault name
    local kv_name
    kv_name=$(ui_input "Key Vault name (Enter to skip)" "")

    echo ""
    ui_info "Provisioning projects: $projects_str"
    ui_info "Target: devuser@$FQDN"
    echo ""

    BOARD_PROJECTS="$projects_str" DEVVM_PROJECTS="$projects_str" bash "${SCRIPT_DIR}/provision-projects.sh" \
        "$FQDN" "$KEY_PATH" "devuser" "$kv_name" "$manifest_dir"
}

# ── Export connection bundle ──

admin_export_bundle() {
    _select_env || return 0
    _select_vm "$ENV" || return 0
    _derive_vm_info "$VM_NAME"

    echo ""
    ui_info "Exporting bundle for $DEV_NAME (env=$ENV)..."
    echo ""

    bash "${SCRIPT_DIR}/export-bundle.sh" "$DEV_NAME" "$ENV" "$DEFAULT_LOCATION" "$DEFAULT_REGION"

    echo ""
    ui_divider
    ui_warn "Remember: send the .board-pass file and passphrase via SEPARATE channels."
    ui_info "  e.g. file via Teams, passphrase verbally or via a different channel."
}

# ── Manage Key Vault secrets ──

admin_manage_secrets() {
    local kv_name
    kv_name=$(ui_input "Key Vault name" "kv-devvm-secrets")

    # Check if KV exists
    if ! az keyvault show --name "$kv_name" --query 'name' -o tsv &>/dev/null; then
        ui_warn "Key Vault '$kv_name' does not exist."
        if ui_confirm "Create Key Vault '$kv_name'?"; then
            local rg_name location
            rg_name=$(ui_input "Resource group for Key Vault" "")
            location=$(ui_input "Location" "$DEFAULT_LOCATION")
            create_keyvault "$kv_name" "$rg_name" "$location"
        else
            ui_info "Cancelled"
            return
        fi
    else
        ui_success "Key Vault '$kv_name' exists"
    fi

    # Collect all expected secrets from manifests
    local manifest_dir="${SCRIPT_DIR}/../projects"
    local manifests=()
    for f in "${manifest_dir}"/*.project.yaml; do
        [[ -f "$f" ]] || continue
        manifests+=("$f")
    done

    local expected_secrets=()
    if (( ${#manifests[@]} > 0 )); then
        while IFS= read -r secret; do
            [[ -z "$secret" ]] && continue
            expected_secrets+=("$secret")
        done < <(manifest_get_keyvault_secrets "${manifests[@]}")
    fi

    while true; do
        echo ""
        if (( ${#expected_secrets[@]} > 0 )); then
            ui_header "Secret Status"
            list_keyvault_status "$kv_name" "${expected_secrets[@]}"
        else
            ui_info "No secrets defined in project manifests"
        fi

        echo ""
        local secret_action
        secret_action=$(ui_choose "What would you like to do?" \
            "Set a secret" \
            "Back")

        case "$secret_action" in
            *"Set a secret"*)
                local secret_name
                secret_name=$(ui_input "Secret name" "")
                if [[ -z "$secret_name" ]]; then
                    ui_warn "No secret name provided"
                    continue
                fi
                set_keyvault_secret_interactive "$kv_name" "$secret_name"
                ;;
            *"Back"*)
                return
                ;;
        esac
    done
}

# ── Health checks ──

admin_health_checks() {
    _select_env || return 0
    _select_vm "$ENV" || return 0
    _derive_vm_info "$VM_NAME"

    echo ""
    ui_info "Running health checks on board $FQDN..."
    echo ""

    bash "${SCRIPT_DIR}/validate-deployment.sh" "$FQDN" "$KEY_PATH"
}

# ── Fleet status ──

_show_fleet_status() {
    local env_names=()
    for f in "${SCRIPT_DIR}/../infra/config/"*.bicepparam; do
        [[ -f "$f" ]] || continue
        env_names+=("$(basename "$f" .bicepparam)")
    done

    (( ${#env_names[@]} == 0 )) && return

    local has_vms=false
    for env_name in "${env_names[@]}"; do
        local rg="rg-${env_name}-${DEFAULT_REGION}-devvm"
        local vm_list
        vm_list=$(az vm list --resource-group "$rg" --show-details \
            --query '[].{name:name, status:powerState}' -o tsv 2>/dev/null) || continue

        [[ -z "$vm_list" ]] && continue
        has_vms=true

        while IFS=$'\t' read -r name status; do
            local dot
            case "$status" in
                *running*)    dot="${_green}●${_reset}" ;;
                *deallocat*)  dot="${_dim}○${_reset}" ;;
                *)            dot="${_yellow}◉${_reset}" ;;
            esac
            echo "  ${dot} ${name}  ${_dim}(${status})${_reset}"
        done <<< "$vm_list"
    done

    if $has_vms; then
        echo ""
    fi
}

# ── Main loop ──

while true; do
    echo ""
    ui_banner "Board Control" "Manage boards, projects, and secrets"

    _show_fleet_status

    ACTION=$(ui_choose "What do you want to do?" \
        "Manage boards" \
        "Wax a board" \
        "Create a board pass" \
        "Manage Key Vault secrets" \
        "Run health checks" \
        "Exit")

    case "$ACTION" in
        *"Manage boards"*)      admin_manage_vms ;;
        *"Wax a board"*)        admin_provision_projects ;;
        *"board pass"*)         admin_export_bundle ;;
        *"Key Vault"*)          admin_manage_secrets ;;
        *"health"*)             admin_health_checks ;;
        *"Exit"*)               echo ""; exit 0 ;;
    esac
done
