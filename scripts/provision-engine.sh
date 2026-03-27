#!/usr/bin/env bash
set -euo pipefail

# Provisioning Engine — reads a project manifest and provisions a remote VM via SSH
# Usage: provision-engine.sh <hostname> <ssh-key-path> <manifest-path> [user] [keyvault-name]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ui.sh
source "${SCRIPT_DIR}/lib/ui.sh"
# shellcheck source=lib/manifest.sh
source "${SCRIPT_DIR}/lib/manifest.sh"

# ── Parse arguments ──

FORCE=false
QUIET=false
POSITIONAL=()
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=true ;;
        --quiet) QUIET=true ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done
set -- "${POSITIONAL[@]}"

if [[ $# -lt 3 ]]; then
    echo "Usage: provision-engine.sh <hostname> <ssh-key-path> <manifest-path> [user] [keyvault-name] [--force] [--quiet]" >&2
    exit 1
fi

HOST="$1"
KEY_PATH="$2"
MANIFEST="$3"
USER="${4:-devuser}"
KV_NAME="${5:-}"

PROJECT_NAME=$(manifest_get "$MANIFEST" '.name')
PROJECT_PATH=$(manifest_get "$MANIFEST" '.path')
# Expand ~ to /home/$USER
PROJECT_PATH="${PROJECT_PATH/#\~//home/$USER}"
REPO=$(manifest_get "$MANIFEST" '.repo')

WARNINGS=()
ERRORS=()

# ── Quiet-mode overrides ──
# When --quiet, suppress all visual output; log to BOARD_PROVISION_LOG

_log() {
    echo "$@" >> "${BOARD_PROVISION_LOG:-/dev/null}" 2>/dev/null || true
}

if $QUIET; then
    ui_step()    { :; }
    ui_banner()  { :; }
    ui_header()  { :; }
    ui_success() { _log "  OK: $1"; }
    ui_error()   { _log "  ERR: $1"; }
    ui_warn()    { _log "  WARN: $1"; }
    ui_info()    { _log "  INFO: $1"; }
    ui_divider() { :; }
fi

# ── SSH helpers ──

_ssh() {
    ssh -i "$KEY_PATH" -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
        -o BatchMode=yes -o LogLevel=ERROR "$USER@$HOST" "$@"
}

_scp() {
    scp -i "$KEY_PATH" -o StrictHostKeyChecking=accept-new \
        -o LogLevel=ERROR "$@"
}

# ── Phase 1: Validate requirements ──

phase_validate() {
    ui_step 1 9 "Validate requirements"

    local max_attempts=6
    local retry_delay=15
    local is_final=false

    for attempt in $(seq 1 $max_attempts); do
        local has_error=false
        (( attempt == max_attempts )) && is_final=true

        # Check required tools
        local tools
        tools=$(manifest_get "$MANIFEST" '.requires.tools[]')
        while IFS= read -r tool; do
            [[ -z "$tool" || "$tool" == "null" ]] && continue
            if _ssh "command -v $tool" &>/dev/null; then
                # Only print success on first attempt or final successful pass
                if (( attempt == 1 )) || $is_final; then
                    ui_success "$tool found"
                fi
            else
                if $is_final; then
                    ui_error "$tool not found on VM"
                    ERRORS+=("Required tool '$tool' missing on VM")
                fi
                has_error=true
            fi
        done <<< "$tools"

        # Check cloud-init completion
        local needs_cloud_init
        needs_cloud_init=$(manifest_get "$MANIFEST" '.requires.cloud_init')
        if [[ "$needs_cloud_init" == "true" ]]; then
            if _ssh "test -f ~/.cloud-init-complete" &>/dev/null; then
                if (( attempt == 1 )) || $is_final; then
                    ui_success "cloud-init complete"
                fi
            else
                if $is_final; then
                    ui_error "cloud-init has not completed (~/.cloud-init-complete missing)"
                    ERRORS+=("cloud-init has not completed on VM")
                fi
                has_error=true
            fi
        fi

        if ! $has_error; then
            if (( attempt > 1 )); then
                ui_success "All tools ready (after $attempt attempts)"
                # Print what was found since we suppressed on intermediate attempts
                while IFS= read -r tool; do
                    [[ -z "$tool" || "$tool" == "null" ]] && continue
                    ui_success "$tool found"
                done <<< "$tools"
            fi
            return 0
        fi

        if (( attempt < max_attempts )); then
            ui_info "Some tools not ready, retrying in ${retry_delay}s (attempt $attempt/$max_attempts, cloud-init may still be running)..."
            _log "Validation attempt $attempt/$max_attempts failed, retrying in ${retry_delay}s..."
            sleep "$retry_delay"
        fi
    done

    return 1
}

# ── Phase 2: Clone repository ──

phase_clone() {
    ui_step 2 9 "Clone repository"

    if _ssh "test -d '$PROJECT_PATH'" &>/dev/null; then
        ui_info "Repository already exists at $PROJECT_PATH, pulling latest..."
        local pull_output
        if pull_output=$(_ssh "cd '$PROJECT_PATH' && git pull" 2>&1); then
            ui_success "Pulled latest changes"
        else
            WARNINGS+=("git pull failed for $PROJECT_NAME")
            ui_warn "git pull did not complete"
            _log "[$PROJECT_NAME] git pull error: $pull_output"
        fi
    else
        ui_info "Cloning $REPO to $PROJECT_PATH..."
        local clone_output
        if clone_output=$(_ssh "git clone '$REPO' '$PROJECT_PATH'" 2>&1); then
            ui_success "Cloned $REPO"
        else
            ui_error "Failed to clone $REPO"
            _log "[$PROJECT_NAME] git clone error: $clone_output"
            ERRORS+=("Failed to clone $REPO to $PROJECT_PATH")
            return 1
        fi
    fi

    # Install Time to First Commit hook
    local hook_content
    hook_content=$(cat << 'HOOK'
#!/usr/bin/env bash
# Board: Time to First Commit measurement (one-time, self-removing)
if [[ -f ~/.board/shaped_at ]] && [[ ! -f ~/.board/first_push_at ]]; then
    date -Iseconds > ~/.board/first_push_at
    shaped=$(date -d "$(cat ~/.board/shaped_at)" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "$(cat ~/.board/shaped_at | cut -c1-19)" +%s 2>/dev/null || echo 0)
    pushed=$(date -d "$(cat ~/.board/first_push_at)" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "$(cat ~/.board/first_push_at | cut -c1-19)" +%s 2>/dev/null || echo 0)
    if (( shaped > 0 && pushed > 0 )); then
        delta=$(( (pushed - shaped) / 60 ))
        cat > ~/.board/metrics.json << METRICS
{
  "time_to_first_commit_minutes": $delta,
  "shaped_at": "$(cat ~/.board/shaped_at)",
  "first_push_at": "$(cat ~/.board/first_push_at)",
  "board_version": "1.0.0"
}
METRICS
        echo ""
        echo "  First push! Time to first commit: ${delta} minutes"
        echo ""
    fi
    # Self-remove from all project hooks
    find ~/projects -name "pre-push" -path "*/.git/hooks/*" -exec grep -l "Board: Time to First Commit" {} \; | xargs rm -f 2>/dev/null
fi
HOOK
)

    _ssh "mkdir -p '${PROJECT_PATH}/.git/hooks'" &>/dev/null || true
    echo "$hook_content" | _ssh "cat > '${PROJECT_PATH}/.git/hooks/pre-push' && chmod +x '${PROJECT_PATH}/.git/hooks/pre-push'"
    ui_success "Installed TTFC pre-push hook"
}

# ── Phase 3: Populate .env (hybrid approach) ──

phase_env() {
    ui_step 3 9 "Populate .env"

    local env_file
    env_file=$(manifest_get "$MANIFEST" '.env.file')

    # If no env block, skip
    if [[ -z "$env_file" ]]; then
        ui_info "No env block in manifest, skipping"
        return 0
    fi

    if [[ -n "$KV_NAME" ]]; then
        ui_info "Generating env provisioning script (Key Vault: $KV_NAME)..."

        # Build the self-contained env script locally
        local tmp_script
        tmp_script=$(mktemp /tmp/env-provision-XXXXXXXX)

        {
            cat <<SCRIPT_HEADER
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="${PROJECT_PATH}/${env_file}"
KV_NAME="${KV_NAME}"

# Ensure target directory exists
mkdir -p "\$(dirname "\$ENV_FILE")"

# Clear the env file
: > "\$ENV_FILE"

# Key Vault secrets
if [[ -n "\${KV_NAME:-}" ]]; then
    # Login with managed identity (retry for RBAC propagation)
    logged_in=false
    for attempt in \$(seq 1 8); do
        if az login --identity --allow-no-subscriptions 2>/dev/null; then
            logged_in=true
            break
        fi
        echo "  RBAC not ready, retrying in 15s (attempt \$attempt/8)..."
        sleep 15
    done

    if ! \$logged_in; then
        echo "ERROR: Failed to login with managed identity after 8 attempts" >&2
        exit 1
    fi

    # Read each secret
SCRIPT_HEADER

            # Generate a line for each keyvault secret
            local kv_pairs
            kv_pairs=$(yq eval '.env.keyvault_secrets | to_entries | .[] | .key + "=" + .value' "$MANIFEST" 2>/dev/null)
            while IFS='=' read -r env_var kv_secret_name; do
                [[ -z "$env_var" || "$env_var" == "null" ]] && continue
                cat <<SECRETLINE
    secret_val=\$(az keyvault secret show --vault-name "\$KV_NAME" --name "${kv_secret_name}" --query 'value' -o tsv 2>/dev/null || echo "")
    echo "${env_var}=\${secret_val}" >> "\$ENV_FILE"
SECRETLINE
            done <<< "$kv_pairs"

            echo "fi"
            echo ""

            # Hardcoded values
            echo "# Hardcoded values"
            local hc_pairs
            hc_pairs=$(yq eval '.env.hardcoded | to_entries | .[] | .key + "=" + .value' "$MANIFEST" 2>/dev/null)
            while IFS='=' read -r key val; do
                [[ -z "$key" || "$key" == "null" ]] && continue
                echo "echo \"${key}=${val}\" >> \"\$ENV_FILE\""
            done <<< "$hc_pairs"
        } > "$tmp_script"

        # Ensure remote staging directory exists
        _ssh "mkdir -p ~/projects/.board" &>/dev/null || true

        # Upload the script
        _scp "$tmp_script" "$USER@$HOST:~/projects/.board/env-${PROJECT_NAME}.sh" &>/dev/null

        # Clean up local temp file
        rm -f "$tmp_script"

        # Execute on the VM
        if _ssh "bash ~/projects/.board/env-${PROJECT_NAME}.sh"; then
            ui_success ".env populated via Key Vault"
        else
            WARNINGS+=("env provisioning script failed for $PROJECT_NAME — secrets may be incomplete")
            ui_warn "env provisioning script returned errors"
        fi
    else
        # No Key Vault — use fallback
        local fallback
        fallback=$(manifest_get "$MANIFEST" '.env.fallback')
        if [[ -n "$fallback" ]]; then
            ui_info "No Key Vault specified, copying fallback ($fallback)..."
            if _ssh "cp '${PROJECT_PATH}/${fallback}' '${PROJECT_PATH}/${env_file}'" &>/dev/null; then
                ui_success ".env populated from fallback ($fallback)"
            else
                WARNINGS+=("Failed to copy fallback env file for $PROJECT_NAME")
                ui_warn "Failed to copy $fallback to $env_file"
            fi
        else
            ui_info "No Key Vault and no fallback defined, skipping .env"
        fi
    fi
}

# ── Phase 4: Install dependencies ──

phase_install() {
    ui_step 4 9 "Install dependencies"

    local count
    count=$(yq eval '.install | length' "$MANIFEST" 2>/dev/null)
    if [[ -z "$count" || "$count" == "null" || "$count" == "0" ]]; then
        ui_info "No install steps defined, skipping"
        return 0
    fi

    for (( i = 0; i < count; i++ )); do
        local label run_cmd
        label=$(manifest_get "$MANIFEST" ".install[$i].label")
        run_cmd=$(manifest_get "$MANIFEST" ".install[$i].run")

        ui_info "$label..."
        local output
        if output=$(_ssh "cd '$PROJECT_PATH' && $run_cmd" 2>&1); then
            ui_success "$label done"
        else
            WARNINGS+=("Install step '$label' did not complete for $PROJECT_NAME")
            ui_warn "$label did not complete"
            _log "[$PROJECT_NAME] $label failed:"
            _log "$output"
        fi
    done
}

# ── Phase 5: Docker services ──

phase_docker() {
    ui_step 5 9 "Docker services"

    local compose_file
    compose_file=$(manifest_get "$MANIFEST" '.docker.compose_file')
    if [[ -z "$compose_file" ]]; then
        ui_info "No docker block defined, skipping"
        return 0
    fi

    ui_info "Starting docker compose services..."
    local compose_output
    if compose_output=$(_ssh "cd '$PROJECT_PATH' && docker compose -f '$compose_file' up -d" 2>&1); then
        ui_success "docker compose up"
    else
        WARNINGS+=("docker compose up failed for $PROJECT_NAME")
        ui_warn "docker compose up failed"
        _log "[$PROJECT_NAME] docker compose error: $compose_output"
        return 0
    fi

    # Set restart policies and poll health for each container
    local container_count
    container_count=$(yq eval '.docker.containers | length' "$MANIFEST" 2>/dev/null)
    [[ -z "$container_count" || "$container_count" == "null" ]] && container_count=0

    for (( i = 0; i < container_count; i++ )); do
        local cname restart_policy health_cmd health_interval health_timeout
        cname=$(manifest_get "$MANIFEST" ".docker.containers[$i].name")
        restart_policy=$(manifest_get "$MANIFEST" ".docker.containers[$i].restart_policy")
        health_cmd=$(manifest_get "$MANIFEST" ".docker.containers[$i].health_cmd")
        health_interval=$(manifest_get "$MANIFEST" ".docker.containers[$i].health_interval")
        health_timeout=$(manifest_get "$MANIFEST" ".docker.containers[$i].health_timeout")

        # Set restart policy
        if [[ -n "$restart_policy" ]]; then
            if _ssh "docker update --restart $restart_policy $cname" &>/dev/null; then
                ui_success "$cname restart policy set to $restart_policy"
            else
                WARNINGS+=("Failed to set restart policy for $cname")
                ui_warn "Failed to set restart policy for $cname"
            fi
        fi

        # Health polling
        if [[ -n "$health_cmd" ]]; then
            local interval="${health_interval:-2}"
            local timeout="${health_timeout:-60}"
            local elapsed=0

            ui_info "Waiting for $cname to become healthy..."
            while (( elapsed < timeout )); do
                if _ssh "docker exec $cname $health_cmd" &>/dev/null; then
                    ui_success "$cname healthy"
                    break
                fi
                sleep "$interval"
                elapsed=$(( elapsed + interval ))
            done

            if (( elapsed >= timeout )); then
                WARNINGS+=("$cname did not become healthy within ${timeout}s")
                ui_warn "$cname health check timed out after ${timeout}s"
            fi
        fi
    done
}

# ── Phase 6: Post-Docker setup ──

phase_post_docker() {
    ui_step 6 9 "Post-Docker setup"

    local count
    count=$(yq eval '.post_docker | length' "$MANIFEST" 2>/dev/null)
    if [[ -z "$count" || "$count" == "null" || "$count" == "0" ]]; then
        ui_info "No post-docker steps defined, skipping"
        return 0
    fi

    for (( i = 0; i < count; i++ )); do
        local label run_cmd
        label=$(manifest_get "$MANIFEST" ".post_docker[$i].label")
        run_cmd=$(manifest_get "$MANIFEST" ".post_docker[$i].run")

        ui_info "$label..."
        local output
        if output=$(_ssh "cd '$PROJECT_PATH' && $run_cmd" 2>&1); then
            ui_success "$label done"
        else
            WARNINGS+=("Post-docker step '$label' did not complete for $PROJECT_NAME")
            ui_warn "$label did not complete"
            _log "[$PROJECT_NAME] $label failed:"
            _log "$output"
        fi
    done
}

# ── Phase 7: systemd user services ──

phase_services() {
    ui_step 7 9 "systemd user services"

    local count
    count=$(yq eval '.services | length' "$MANIFEST" 2>/dev/null)
    if [[ -z "$count" || "$count" == "null" || "$count" == "0" ]]; then
        ui_info "No services defined, skipping"
        return 0
    fi

    for (( i = 0; i < count; i++ )); do
        local svc_name health_url health_timeout
        svc_name=$(manifest_get "$MANIFEST" ".services[$i].name")
        health_url=$(manifest_get "$MANIFEST" ".services[$i].health_url")
        health_timeout=$(manifest_get "$MANIFEST" ".services[$i].health_timeout")

        ui_info "Setting up $svc_name..."

        # Generate unit file content
        local unit_content
        unit_content=$(manifest_generate_systemd_unit "$MANIFEST" "$i" "$PROJECT_PATH")

        # Create directories and write unit file via SSH
        _ssh "mkdir -p ~/.config/systemd/user" &>/dev/null || true

        # Upload unit file using heredoc over SSH
        _ssh "cat > ~/.config/systemd/user/${svc_name}.service" <<< "$unit_content"

        # Enable and start the service
        if _ssh "systemctl --user daemon-reload && systemctl --user enable --now $svc_name" &>/dev/null; then
            ui_success "$svc_name enabled and started"
        else
            WARNINGS+=("Failed to enable/start $svc_name")
            ui_warn "Failed to enable/start $svc_name"
            continue
        fi

        # Health URL polling
        if [[ -n "$health_url" ]]; then
            local timeout="${health_timeout:-30}"
            local elapsed=0

            ui_info "Waiting for $svc_name health ($health_url)..."
            while (( elapsed < timeout )); do
                if _ssh "curl -sf $health_url" &>/dev/null; then
                    ui_success "$svc_name health check passed"
                    break
                fi
                sleep 2
                elapsed=$(( elapsed + 2 ))
            done

            if (( elapsed >= timeout )); then
                WARNINGS+=("$svc_name health check timed out after ${timeout}s ($health_url)")
                ui_warn "$svc_name health check timed out after ${timeout}s"
            fi
        fi
    done
}

# ── Phase 8: VS Code config ──

phase_vscode() {
    ui_step 8 9 "VS Code configuration"

    # Tasks
    local tasks_count
    tasks_count=$(yq eval '.vscode.tasks | length' "$MANIFEST" 2>/dev/null)
    if [[ -n "$tasks_count" && "$tasks_count" != "null" && "$tasks_count" != "0" ]]; then
        local tasks_file="$PROJECT_PATH/.vscode/tasks.json"
        if ! $FORCE && _ssh "test -f '$tasks_file'" &>/dev/null; then
            ui_info "tasks.json already exists (use --force to overwrite)"
        else
            local tasks_json
            tasks_json=$(manifest_generate_vscode_tasks "$MANIFEST")
            _ssh "mkdir -p '$PROJECT_PATH/.vscode'" &>/dev/null || true
            _ssh "cat > '$tasks_file'" <<< "$tasks_json"
            ui_success "tasks.json written"
        fi
    fi

    # Launch
    local launch_count
    launch_count=$(yq eval '.vscode.launch | length' "$MANIFEST" 2>/dev/null)
    if [[ -n "$launch_count" && "$launch_count" != "null" && "$launch_count" != "0" ]]; then
        local launch_file="$PROJECT_PATH/.vscode/launch.json"
        if ! $FORCE && _ssh "test -f '$launch_file'" &>/dev/null; then
            ui_info "launch.json already exists (use --force to overwrite)"
        else
            local launch_json
            launch_json=$(manifest_generate_vscode_launch "$MANIFEST")
            _ssh "mkdir -p '$PROJECT_PATH/.vscode'" &>/dev/null || true
            _ssh "cat > '$launch_file'" <<< "$launch_json"
            ui_success "launch.json written"
        fi
    fi

    # Settings
    local settings_json
    settings_json=$(manifest_get "$MANIFEST" '.vscode.settings')
    if [[ -n "$settings_json" && "$settings_json" != "null" && "$settings_json" != "{}" ]]; then
        local settings_file="$PROJECT_PATH/.vscode/settings.json"
        if ! $FORCE && _ssh "test -f '$settings_file'" &>/dev/null; then
            ui_info "settings.json already exists (use --force to overwrite)"
        else
            local settings_content
            settings_content=$(manifest_generate_vscode_settings "$MANIFEST")
            _ssh "mkdir -p '$PROJECT_PATH/.vscode'" &>/dev/null || true
            _ssh "cat > '$settings_file'" <<< "$settings_content"
            ui_success "settings.json written"
        fi
    fi

    # If nothing was generated
    if [[ ( -z "$tasks_count" || "$tasks_count" == "null" || "$tasks_count" == "0" ) && \
          ( -z "$launch_count" || "$launch_count" == "null" || "$launch_count" == "0" ) && \
          ( -z "$settings_json" || "$settings_json" == "null" ) ]]; then
        ui_info "No VS Code config defined, skipping"
    fi
}

# ── Phase 9: Health check verification ──

phase_health() {
    ui_step 9 9 "Health check verification"

    local health_count
    health_count=$(yq eval '.health | length' "$MANIFEST" 2>/dev/null)
    if [[ -n "$health_count" && "$health_count" != "null" && "$health_count" != "0" ]]; then
        for (( i = 0; i < health_count; i++ )); do
            local label check_cmd
            label=$(manifest_get "$MANIFEST" ".health[$i].label")
            check_cmd=$(manifest_get "$MANIFEST" ".health[$i].check")

            if _ssh "cd '$PROJECT_PATH' && $check_cmd" &>/dev/null; then
                ui_success "$label: passed"
            else
                WARNINGS+=("Health check '$label' failed for $PROJECT_NAME")
                ui_warn "$label: failed"
            fi
        done
    else
        ui_info "No health checks defined, skipping"
    fi

    # Check required env vars
    local env_file
    env_file=$(manifest_get "$MANIFEST" '.env.file')
    local req_count
    req_count=$(yq eval '.env.required | length' "$MANIFEST" 2>/dev/null)

    if [[ -n "$req_count" && "$req_count" != "null" && "$req_count" != "0" && -n "$env_file" ]]; then
        ui_info "Checking required environment variables..."
        for (( i = 0; i < req_count; i++ )); do
            local var_name
            var_name=$(manifest_get "$MANIFEST" ".env.required[$i]")
            if _ssh "grep -q '^${var_name}=.\+' '${PROJECT_PATH}/${env_file}'" &>/dev/null; then
                ui_success "$var_name is set"
            else
                WARNINGS+=("Required env var '$var_name' is empty or missing in .env for $PROJECT_NAME")
                ui_warn "$var_name is empty or missing in .env"
            fi
        done
    fi

    # Print summary
    ui_divider
    echo ""

    if (( ${#ERRORS[@]} > 0 )); then
        ui_header "Errors (${#ERRORS[@]})"
        for err in "${ERRORS[@]}"; do
            ui_error "$err"
        done
        echo ""
    fi

    if (( ${#WARNINGS[@]} > 0 )); then
        ui_header "Warnings (${#WARNINGS[@]})"
        for warn in "${WARNINGS[@]}"; do
            ui_warn "$warn"
        done
        echo ""
        ui_info "Tip: Re-run with Key Vault name to populate missing secrets"
        ui_info "Tip: Check systemd logs with: journalctl --user -u <service> -f"
        echo ""
    fi

    if (( ${#ERRORS[@]} == 0 && ${#WARNINGS[@]} == 0 )); then
        ui_success "All checks passed for $PROJECT_NAME"
    elif (( ${#ERRORS[@]} == 0 )); then
        ui_success "Provisioning completed with ${#WARNINGS[@]} warning(s)"
    fi
}

# ── Main ──

if ! $QUIET; then
    ui_banner "Board Provisioning Engine" "Project: $PROJECT_NAME -> $USER@$HOST"
fi

# Run all phases
fatal=false

if ! phase_validate; then
    ui_error "Validation failed — cannot proceed with $PROJECT_NAME"
    fatal=true
fi

if ! $fatal; then
    if ! phase_clone; then
        ui_error "Clone failed — cannot proceed with $PROJECT_NAME"
        fatal=true
    fi
fi

if ! $fatal; then
    phase_env
    phase_install
    phase_docker
    phase_post_docker
    phase_services
    phase_vscode
    phase_health
fi

# Write board config and shaped_at timestamp on success
if ! $fatal && (( ${#ERRORS[@]} == 0 )); then
    _ssh "sudo mkdir -p /home/$USER/.board && sudo chown $USER:$USER /home/$USER/.board" &>/dev/null || true
    if _ssh "cat > ~/.board/config << EOF
BOARD_NAME=board-\$(hostname | sed 's/^vm-[a-z]*-[a-z]*-devvm-//')
BOARD_REGION=\$(curl -sf -H Metadata:true 'http://169.254.169.254/metadata/instance/compute/location?api-version=2021-02-01&format=text' 2>/dev/null || echo 'unknown')
BOARD_SIZE=\$(curl -sf -H Metadata:true 'http://169.254.169.254/metadata/instance/compute/vmSize?api-version=2021-02-01&format=text' 2>/dev/null || echo 'unknown')
EOF" 2>/dev/null; then
        ui_success "Board config written to ~/.board/config"
    else
        ui_warn "Could not write ~/.board/config (directory may be owned by root)"
    fi

    if _ssh "date -Iseconds > ~/.board/shaped_at" 2>/dev/null; then
        ui_success "Recorded board creation timestamp"
    else
        ui_warn "Could not write ~/.board/shaped_at"
    fi
fi

# Exit code: 0 if no fatal errors, 1 if any
if $fatal || (( ${#ERRORS[@]} > 0 )); then
    exit 1
fi
exit 0
