#!/usr/bin/env bash
# Azure Key Vault helper functions
# Sourced by setup.sh (admin-facing) and provisioning engine (VM-facing)
# Requires: scripts/lib/ui.sh sourced first (for ui_* functions)

# ── Admin-facing functions (1-4) ──

ensure_keyvault_secrets_officer() {
    local name="$1"
    local user_oid
    user_oid=$(az ad signed-in-user show --query id -o tsv 2>/dev/null)
    if [[ -n "$user_oid" ]]; then
        local kv_id
        kv_id=$(az keyvault show --name "$name" --query id -o tsv 2>/dev/null)
        # Check if assignment already exists before creating
        if az role assignment list --assignee "$user_oid" --scope "$kv_id" \
            --role "Key Vault Secrets Officer" --query '[0].id' -o tsv 2>/dev/null | grep -q .; then
            return 0
        fi
        # shellcheck disable=SC2015 # A && B || C is intentional — B failing is acceptable here
        az role assignment create \
            --assignee-object-id "$user_oid" \
            --assignee-principal-type User \
            --role "Key Vault Secrets Officer" \
            --scope "$kv_id" \
            --output none 2>/dev/null && \
            ui_success "Secrets Officer role assigned" || \
            ui_warn "Could not assign Secrets Officer role — you may need to set secrets manually"
        # RBAC propagation can take a moment
        sleep 10
    fi
}

create_keyvault() {
    local name="$1"
    local rg_name="$2"
    local location="$3"

    if az keyvault show --name "$name" --query 'name' -o tsv 2>/dev/null; then
        ui_success "Key Vault '$name' already exists"
        ensure_keyvault_secrets_officer "$name"
        return 0
    fi

    # Recover soft-deleted vault if it exists
    if az keyvault show-deleted --name "$name" --query 'name' -o tsv 2>/dev/null | grep -q .; then
        ui_info "Recovering soft-deleted Key Vault '$name'..."
        if az keyvault recover --name "$name" --output none; then
            ui_success "Key Vault '$name' recovered"
            ensure_keyvault_secrets_officer "$name"
            return 0
        else
            ui_error "Failed to recover Key Vault '$name'. Purge it manually: az keyvault purge --name $name"
            return 1
        fi
    fi

    if az keyvault create --name "$name" --resource-group "$rg_name" --location "$location" --output none; then
        ui_success "Key Vault '$name' created"
        ensure_keyvault_secrets_officer "$name"
        return 0
    else
        # Bug 1 fix: vault may be in limbo (recently deleted, not yet queryable as soft-deleted)
        ui_warn "Key Vault create failed — checking for soft-delete conflict..."
        local kv_retry_delay="${BOARD_KV_RETRY_DELAY:-10}"
        local retry
        for retry in 1 2 3; do
            sleep "$kv_retry_delay"
            if az keyvault show-deleted --name "$name" --query 'name' -o tsv 2>/dev/null | grep -q .; then
                ui_info "Found soft-deleted vault (attempt $retry), purging..."
                if az keyvault purge --name "$name" 2>/dev/null; then
                    sleep "$kv_retry_delay"
                    if az keyvault create --name "$name" --resource-group "$rg_name" --location "$location" --output none; then
                        ui_success "Key Vault '$name' created (after purge)"
                        ensure_keyvault_secrets_officer "$name"
                        return 0
                    fi
                fi
            fi
            ui_info "Retry $retry/3 — waiting for soft-delete state to settle..."
        done
        ui_error "Failed to create Key Vault '$name' after retries. Manual fix: az keyvault purge --name $name"
        return 1
    fi
}

resolve_keyvault_id() {
    local name="$1"
    timeout 30 az keyvault show --name "$name" --query 'id' -o tsv 2>/dev/null
}

set_keyvault_secret_interactive() {
    local kv_name="$1"
    local secret_name="$2"

    ui_info "  $secret_name:"

    local value
    read -s -rp "    Value (Enter to skip): " value </dev/tty
    echo ""  # newline after masked input

    if [[ -z "$value" ]]; then
        ui_warn "Skipped $secret_name"
        return 0
    fi

    if az keyvault secret set --vault-name "$kv_name" --name "$secret_name" --value "$value" --output none; then
        ui_success "Set $secret_name"
    else
        ui_error "Failed to set $secret_name"
        return 1
    fi
}

list_keyvault_status() {
    local kv_name="$1"
    shift
    local expected_secrets=("$@")

    local name
    for name in "${expected_secrets[@]}"; do
        local val
        val=$(az keyvault secret show --vault-name "$kv_name" --name "$name" --query 'value' -o tsv 2>/dev/null)
        if [[ -n "$val" ]]; then
            ui_success "$name ... set"
        else
            ui_warn "$name ... not set"
        fi
    done
}

# ── VM-facing function (5) ──

read_keyvault_secrets_to_env() {
    local kv_name="$1"
    local manifest_path="$2"
    local output_file="$3"

    # ── Login with managed identity (retry for RBAC propagation) ──
    local max_retries=8
    local retry_delay=15
    local attempt=0
    local logged_in=false

    while (( attempt < max_retries )); do
        if az login --identity --allow-no-subscriptions 2>/dev/null; then
            logged_in=true
            break
        fi
        (( attempt++ ))
        if (( attempt < max_retries )); then
            sleep "$retry_delay"
        fi
    done

    if ! $logged_in; then
        ui_error "Failed to login with managed identity after $max_retries attempts"
        return 1
    fi

    # Clear output file
    : > "$output_file"

    # ── Read keyvault_secrets from manifest ──
    local missing_required=()
    local kv_pairs
    kv_pairs=$(yq eval '.env.keyvault_secrets | to_entries | .[] | .key + "=" + .value' "$manifest_path" 2>/dev/null)

    while IFS='=' read -r env_var kv_secret_name; do
        [[ -z "$env_var" || "$env_var" == "null" ]] && continue
        local value
        value=$(az keyvault secret show --vault-name "$kv_name" --name "$kv_secret_name" --query 'value' -o tsv 2>/dev/null || echo "")
        echo "${env_var}=${value}" >> "$output_file"
    done <<< "$kv_pairs"

    # ── Read hardcoded values from manifest ──
    local hc_pairs
    hc_pairs=$(yq eval '.env.hardcoded | to_entries | .[] | .key + "=" + .value' "$manifest_path" 2>/dev/null)

    while IFS='=' read -r key val; do
        [[ -z "$key" || "$key" == "null" ]] && continue
        echo "${key}=${val}" >> "$output_file"
    done <<< "$hc_pairs"

    # ── Check required env vars ──
    local required_vars
    required_vars=$(yq eval '.env.required[]' "$manifest_path" 2>/dev/null)

    while IFS= read -r req_var; do
        [[ -z "$req_var" || "$req_var" == "null" ]] && continue
        local found_val
        found_val=$(grep "^${req_var}=" "$output_file" 2>/dev/null | head -1 | cut -d'=' -f2-)
        if [[ -z "$found_val" ]]; then
            missing_required+=("$req_var")
        fi
    done <<< "$required_vars"

    # Return missing required secrets (one per line on stdout for caller to capture)
    if (( ${#missing_required[@]} > 0 )); then
        printf '%s\n' "${missing_required[@]}"
    fi
}
