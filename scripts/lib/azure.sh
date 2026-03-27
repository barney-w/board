#!/usr/bin/env bash
# Azure CLI helper functions for Board setup

ensure_az_login() {
    if timeout 15 az account show &>/dev/null; then
        local name user sub_id
        user=$(timeout 10 az account show --query 'user.name' -o tsv 2>/dev/null)
        name=$(timeout 10 az account show --query 'name' -o tsv 2>/dev/null)
        sub_id=$(timeout 10 az account show --query 'id' -o tsv 2>/dev/null)
        ui_success "Logged in as $user"
        ui_info "Subscription: $name ($sub_id)"
        echo ""

        if ! ui_confirm "Use this subscription?"; then
            select_subscription
        fi
        return 0
    else
        ui_warn "Not logged in to Azure"
        echo ""
        echo "  Opening browser for Azure login..."
        echo ""
        if az login --output none 2>&1; then
            ui_success "Login successful"
            return 0
        else
            ui_error "Azure login failed"
            return 1
        fi
    fi
}

select_subscription() {
    local subs
    subs=$(az account list --query '[].[name, id]' -o tsv 2>/dev/null)
    if [[ -z "$subs" ]]; then
        ui_error "No subscriptions found"
        return 1
    fi

    local names=()
    local ids=()
    while IFS=$'\t' read -r name id; do
        names+=("$name")
        ids+=("$id")
    done <<< "$subs"

    local chosen
    chosen=$(ui_choose "Select a subscription:" "${names[@]}")

    local idx=0
    for name in "${names[@]}"; do
        if [[ "$name" == "$chosen" ]]; then
            az account set --subscription "${ids[$idx]}" --output none
            ui_success "Switched to: $chosen"
            return 0
        fi
        ((idx++))
    done
}

ensure_resource_group() {
    local rg_name="$1"
    local location="$2"
    local environment="$3"

    # Check if RG exists and what state it's in
    local rg_state
    rg_state=$(timeout 30 az group show --name "$rg_name" --query 'properties.provisioningState' -o tsv 2>/dev/null || echo "")

    if [[ "$rg_state" == "Deleting" ]]; then
        ui_info "Resource group $rg_name is being deleted from a previous run. Waiting..."
        local wait_start=$SECONDS
        while [[ "$rg_state" == "Deleting" ]]; do
            if (( SECONDS - wait_start > 600 )); then
                ui_error "Resource group $rg_name still deleting after 10 minutes. Try again later."
                return 1
            fi
            sleep 10
            rg_state=$(timeout 30 az group show --name "$rg_name" --query 'properties.provisioningState' -o tsv 2>/dev/null || echo "")
        done
        # Verify it's actually gone (not transitioned to a failed state)
        if [[ -n "$rg_state" && "$rg_state" != "Succeeded" ]]; then
            ui_error "Resource group $rg_name in unexpected state after deletion: $rg_state"
            return 1
        fi
        ui_success "Previous resource group deletion completed"
    elif [[ "$rg_state" == "Succeeded" ]]; then
        ui_success "Resource group $rg_name already exists"
        return 0
    elif [[ -n "$rg_state" ]]; then
        # Handle unexpected states like "Failed", "Updating", etc.
        ui_error "Resource group $rg_name is in state '$rg_state'. Delete it first: just destroy-all"
        return 1
    fi

    ui_info "Creating resource group $rg_name..."
    if timeout 60 az group create \
        --name "$rg_name" \
        --location "$location" \
        --tags project=devvm environment="$environment" managed-by=bicep \
        --output none 2>&1; then
        ui_success "Resource group $rg_name created"
        return 0
    else
        ui_error "Failed to create resource group $rg_name"
        return 1
    fi
}

deploy_vm() {
    local rg_name="$1"
    local env_name="$2"
    local dev_name="$3"
    local vm_sku="$4"
    local ssh_pub_key="$5"
    local script_dir="$6"
    local kv_resource_id="${7:-}"
    local deployment_name
    deployment_name="deploy-${dev_name}-$(date -u +%Y%m%d%H%M%S)"

    local start_time=$SECONDS

    # Bicep's readEnvironmentVariable() is evaluated at compile time,
    # so SSH_PUB_KEY must exist even though --parameters overrides it.
    export SSH_PUB_KEY="$ssh_pub_key"

    # Build extra Bicep parameters conditionally
    local extra_params=""
    if [[ -n "$kv_resource_id" ]]; then
        extra_params="keyVaultResourceId=$kv_resource_id"
    fi

    _deploy_elapsed() {
        local e=$(( SECONDS - start_time ))
        printf "%dm %ds" $(( e / 60 )) $(( e % 60 ))
    }

    # Start deployment asynchronously so we can show progress
    local deploy_err
    deploy_err=$(mktemp)
    if ! az deployment group create \
        --resource-group "$rg_name" \
        --template-file "${script_dir}/../infra/main.bicep" \
        --parameters "${script_dir}/../infra/config/${env_name}.bicepparam" \
        --parameters developerName="$dev_name" vmSku="$vm_sku" adminSshPublicKey="$ssh_pub_key" ${extra_params:+"$extra_params"} \
        --name "$deployment_name" \
        --no-wait 2>"$deploy_err"; then
        ui_error "Failed to start deployment"
        cat "$deploy_err" >&2
        rm -f "$deploy_err"
        return 1
    fi
    rm -f "$deploy_err"

    # Poll deployment status with live progress
    local max_wait=900  # 15 minutes
    local spinchars='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0 cols=${COLUMNS:-80}
    while (( SECONDS - start_time < max_wait )); do
        local state
        state=$(az deployment group show \
            --resource-group "$rg_name" \
            --name "$deployment_name" \
            --query 'properties.provisioningState' -o tsv 2>/dev/null) || state=""

        case "$state" in
            Succeeded)
                printf "\r\033[K"
                break
                ;;
            Failed|Canceled)
                printf "\r\033[K"
                ui_error "Deployment $state after $(_deploy_elapsed)"
                echo ""
                az deployment group show \
                    --resource-group "$rg_name" \
                    --name "$deployment_name" \
                    --query 'properties.error' -o json 2>/dev/null | head -30 >&2
                echo ""
                ui_info "Debug with: just what-if $dev_name $env_name"
                ui_info "Clean up with: just destroy-all $env_name"
                return 1
                ;;
            *)
                local char="${spinchars:$((i % ${#spinchars})):1}"
                local line
                line=$(printf "  %s Deploying board... %s (%s)" "$char" "${state:-Starting}" "$(_deploy_elapsed)")
                printf "\r\033[36m%s\033[0m" "${line:0:$cols}"
                ;;
        esac
        sleep 5
        ((i++)) || true
    done

    if (( SECONDS - start_time >= max_wait )); then
        printf "\r\033[K"
        ui_error "Deployment timed out after $(_deploy_elapsed)"
        ui_info "Check status: az deployment group show --resource-group $rg_name --name $deployment_name"
        return 1
    fi

    ui_success "Deployment complete ($(_deploy_elapsed))"

    # Fetch outputs from the completed deployment
    local output
    output=$(az deployment group show \
        --resource-group "$rg_name" \
        --name "$deployment_name" \
        --query 'properties.outputs.{vmName:vmName.value, publicIpAddress:publicIpAddress.value, fqdn:fqdn.value, sshCommand:sshCommand.value}' \
        -o tsv 2>/dev/null)

    # Parse TSV outputs (tab-separated: vmName, publicIpAddress, fqdn, sshCommand)
    IFS=$'\t' read -r DEPLOY_VM_NAME DEPLOY_PUBLIC_IP DEPLOY_FQDN DEPLOY_SSH_CMD <<< "$output"

    # Persist outputs so parent shell can source them
    if [[ -n "${DEPLOY_VARS_FILE:-}" ]]; then
        printf 'DEPLOY_VM_NAME=%q\nDEPLOY_PUBLIC_IP=%q\nDEPLOY_FQDN=%q\nDEPLOY_SSH_CMD=%q\n' \
            "$DEPLOY_VM_NAME" "$DEPLOY_PUBLIC_IP" "$DEPLOY_FQDN" "$DEPLOY_SSH_CMD" \
            > "$DEPLOY_VARS_FILE"
    fi

    echo ""
    ui_info "VM Name:    $DEPLOY_VM_NAME"
    ui_info "Public IP:  $DEPLOY_PUBLIC_IP"
    ui_info "FQDN:       $DEPLOY_FQDN"

    return 0
}

wait_for_cloud_init() {
    local hostname="$1"
    local key_path="$2"
    local user="${3:-devuser}"
    local fallback_ip="${4:-}"
    local max_wait=1800  # 30 min absolute safety limit
    local start_time=$SECONDS
    local ssh_connected=false
    local ssh_target=""
    local ssh_opts=(-i "$key_path" -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o LogLevel=ERROR)

    # Clear stale host keys — a (re)deployed VM will have a new host key
    ssh-keygen -R "$hostname" &>/dev/null || true
    if [[ -n "$fallback_ip" ]]; then
        ssh-keygen -R "$fallback_ip" &>/dev/null || true
    fi

    _ci_elapsed() {
        local e=$(( SECONDS - start_time ))
        printf "%dm %ds" $(( e / 60 )) $(( e % 60 ))
    }

    _ci_try_ssh() {
        # shellcheck disable=SC2029 # intentional client-side expansion for SSH commands
        ssh "${ssh_opts[@]}" "$user@$1" "${@:2}" 2>/dev/null
    }

    _ci_spin_wait() {
        local msg="$1"
        local duration="${2:-10}"
        if $USE_GUM; then
            gum spin --spinner dot \
                --title "  $msg ($(_ci_elapsed))" \
                --timeout "${duration}s" -- sleep "$duration" 2>/dev/null || true
        else
            local spinchars='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
            local end_at=$(( SECONDS + duration ))
            local i=0
            local cols=${COLUMNS:-80}
            while (( SECONDS < end_at )); do
                local char="${spinchars:$((i % ${#spinchars})):1}"
                local line
                line=$(printf "  %s %s (%s)" "$char" "$msg" "$(_ci_elapsed)")
                printf "\r\033[36m%s\033[0m" "${line:0:$cols}"
                sleep 0.3 2>/dev/null || sleep 1
                ((i++)) || true
            done
        fi
    }

    _ci_clear_line() {
        if ! $USE_GUM; then
            printf "\r\033[K"
        fi
    }

    # ── Completion check: marker file is the single source of truth ──
    # The marker is the LAST thing cloud-init writes (after all tools).
    # We also verify a few apt-installed tools as a sanity check, but
    # do NOT check tools installed via wget/curl (yq, VS Code CLI) since
    # those external downloads can fail without meaning cloud-init failed.
    #
    # NOTE: This is a quick sanity check for apt-installed tools only.
    # Full manifest-based tool validation happens in provision-engine.sh:phase_validate()
    # which reads .requires.tools[] from each project manifest and retries 6 times.
    _ci_verify_done() {
        local target="$1"
        # The marker file is written as the very last runcmd step
        if ! _ci_try_ssh "$target" "test -f /home/$user/.cloud-init-complete" &>/dev/null; then
            return 1
        fi
        # Single SSH call to verify all tools at once — avoids flaky multi-connection issues
        # Uses 'which' in a login shell to find tools regardless of install path
        _ci_try_ssh "$target" "timeout 10 bash -lc 'which docker node python3'" &>/dev/null
    }

    # ── Phase 1: Wait for SSH connectivity ──
    # Try hostname first; if that fails and we have an IP, try the IP as fallback
    # (covers DNS propagation delays for newly created public IPs)
    while (( SECONDS - start_time < max_wait )); do
        if _ci_try_ssh "$hostname" "true"; then
            ssh_connected=true
            ssh_target="$hostname"
            _ci_clear_line
            ui_success "VM accepting SSH connections ($(_ci_elapsed))"
            break
        fi

        if [[ -n "$fallback_ip" ]] && _ci_try_ssh "$fallback_ip" "true"; then
            ssh_connected=true
            ssh_target="$fallback_ip"
            _ci_clear_line
            ui_success "VM accepting SSH connections via IP ($(_ci_elapsed))"
            ui_info "DNS for $hostname may still be propagating"
            break
        fi

        _ci_spin_wait "Waiting for SSH..."
    done

    if ! $ssh_connected; then
        _ci_clear_line
        ui_error "VM did not become reachable after $(_ci_elapsed)"
        # Diagnostic: show what SSH actually reports
        local diag_target="${fallback_ip:-$hostname}"
        local probe
        probe=$(ssh -i "$key_path" -o ConnectTimeout=5 -o BatchMode=yes -v \
            "$user@$diag_target" "true" 2>&1 | grep -E '(Connection|connect|refused|timed|key|Host key)' | head -5) || true
        if [[ -n "$probe" ]]; then
            ui_info "SSH diagnostic ($diag_target):"
            # shellcheck disable=SC2001 # sed is clearer than ${//} for line-prefix insertion
            echo "$probe" | sed 's/^/    /'
        fi
        ui_info "Check VM status: just list"
        return 1
    fi

    # ── Phase 2: Wait for cloud-init (status-aware, tool-verified) ──
    echo ""
    ui_info "Now installing Docker, Python, Node.js, and dev tools."
    ui_info "This usually takes 5-8 minutes."
    echo ""

    local last_progress=""
    local stale_done_count=0  # Detect stale "done" from prior boot

    # Use timeout on remote commands — cloud-init status can hang if dpkg lock is held
    local marker_seen=false  # Sticky — once marker seen, never unset
    while (( SECONDS - start_time < max_wait )); do
        local ci_output
        ci_output=$(_ci_try_ssh "$ssh_target" "timeout 10 cloud-init status 2>/dev/null") || ci_output="status: unknown"

        # Also check marker directly — works even if cloud-init status hangs
        local has_marker=false
        _ci_try_ssh "$ssh_target" "test -f /home/$user/.cloud-init-complete" && has_marker=true
        $has_marker && marker_seen=true

        # ── Fast path: marker exists (cloud-init wrote it as the very last step) ──
        # The marker IS the source of truth. Verify tools as a sanity check,
        # but don't block indefinitely on it — SSH can be flaky under load.
        if $marker_seen; then
            if _ci_verify_done "$ssh_target"; then
                _ci_clear_line
                if echo "$ci_output" | grep -q "status: error"; then
                    ui_warn "Cloud-init had errors but bootstrap completed ($(_ci_elapsed))"
                    ui_info "Some non-critical installs may have failed. Run: just smoke-test <name>"
                else
                    ui_success "Cloud-init complete ($(_ci_elapsed))"
                fi
                return 0
            fi
            # Marker exists but verify failed — likely SSH flakiness, not missing tools.
            # Give it a few attempts then trust the marker.
            (( stale_done_count++ )) || true
            if (( stale_done_count >= 3 )); then
                _ci_clear_line
                ui_warn "Cloud-init marker present but tool verify timed out ($(_ci_elapsed))"
                ui_info "Proceeding — provision engine will do full validation next."
                return 0
            fi
        elif echo "$ci_output" | grep -q "status: done"; then
            # cloud-init says done but no marker — stale status from prior boot
            (( stale_done_count++ )) || true
            if (( stale_done_count >= 6 )); then
                _ci_clear_line
                ui_error "Cloud-init reports 'done' but marker file is missing ($(_ci_elapsed))"
                ui_info "This usually means cloud-init ran on a previous boot but failed on this one."
                ui_info "Debug: just ssh <name>, then: sudo cloud-init status --long"
                ui_info "Re-run cloud-init: sudo cloud-init clean && sudo reboot"
                return 1
            fi
        elif echo "$ci_output" | grep -q "status: error"; then
            if ! $has_marker; then
                _ci_clear_line
                ui_error "Cloud-init failed before completing bootstrap"
                echo ""
                local detail
                detail=$(_ci_try_ssh "$ssh_target" "timeout 10 cloud-init status --long 2>/dev/null") || true
                if [[ -n "$detail" ]]; then
                    # shellcheck disable=SC2001 # sed is clearer than ${//} for line-prefix insertion
                    echo "$detail" | sed 's/^/    /'
                fi
                echo ""
                ui_info "View log: just ssh <name>, then: sudo tail -50 /var/log/cloud-init-output.log"
                return 1
            fi
            # Marker exists handled by the marker_seen path above
        elif echo "$ci_output" | grep -q "status: running"; then
            stale_done_count=0  # Reset only when actively running
        fi

        # Fetch latest progress line from cloud-init log
        local progress
        progress=$(_ci_try_ssh "$ssh_target" \
            "tail -5 /var/log/cloud-init-output.log 2>/dev/null | grep -v '^\$' | tail -1 | tr '\r' '\n' | grep -v '^\$' | tail -1 | tr -cd '[:print:] ' | cut -c1-80" \
        ) || progress=""
        [[ -z "$progress" ]] && progress="Installing development tools..."
        # Don't show "complete" while still polling — it contradicts the UX
        if echo "$progress" | grep -qi "complete\|ready for development"; then
            progress="Finalizing installation..."
        fi

        # Always update display (elapsed time changes even if progress text doesn't)
        _ci_clear_line
        local cols=${COLUMNS:-80}
        local line
        line=$(printf "  › %s (%s)" "$progress" "$(_ci_elapsed)")
        printf "\r\033[2m%s\033[0m" "${line:0:$cols}"
        if [[ "$progress" != "$last_progress" ]]; then
            last_progress="$progress"
        fi
        sleep 10
    done

    # Absolute timeout (shouldn't happen in practice)
    _ci_clear_line
    ui_error "Cloud-init still running after 30 minutes"
    ui_info "Check: just cloud-init-status <name>"
    return 1
}

check_existing_vm() {
    local rg_name="$1"
    local vm_name="$2"

    timeout 30 az vm show --resource-group "$rg_name" --name "$vm_name" --query 'name' -o tsv 2>/dev/null
}
