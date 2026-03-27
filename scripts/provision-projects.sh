#!/usr/bin/env bash
set -euo pipefail

# Board Waxer — discovers manifests, provisions each project,
# then generates cross-project artifacts (workspace file, check script, manifest copies).
# Usage: provision-projects.sh <hostname> <ssh-key-path> [user] [keyvault-name] [manifest-dir] [--quiet]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ui.sh
source "${SCRIPT_DIR}/lib/ui.sh"
# shellcheck source=lib/manifest.sh
source "${SCRIPT_DIR}/lib/manifest.sh"

# ── Parse flags ──

QUIET="${BOARD_QUIET:-false}"
POSITIONAL=()
for arg in "$@"; do
    case "$arg" in
        --quiet) QUIET=true ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done
set -- "${POSITIONAL[@]}"

if [[ $# -lt 2 ]]; then
    echo "Usage: provision-projects.sh <hostname> <ssh-key-path> [user] [keyvault-name] [manifest-dir] [--quiet]" >&2
    exit 1
fi

HOST="$1"
KEY_PATH="$2"
USER="${3:-devuser}"
KV_NAME="${4:-}"
MANIFEST_DIR="${5:-${SCRIPT_DIR}/../projects}"

# ── Quiet-mode overrides ──

_log() {
    echo "$@" >> "${BOARD_PROVISION_LOG:-/dev/null}" 2>/dev/null || true
}

if $QUIET; then
    ui_step()       { :; }
    ui_banner()     { :; }
    ui_header()     { :; }
    ui_summary_box() { :; }
    ui_success()    { _log "  OK: $1"; }
    ui_error()      { _log "  ERR: $1"; }
    ui_warn()       { _log "  WARN: $1"; }
    ui_info()       { _log "  INFO: $1"; }
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

# ── Timing ──

START_TIME=$SECONDS

# ── Step 1: Discover manifests ──

if ! $QUIET; then
    ui_banner "Board Waxer" "Provisioning projects on $USER@$HOST"
fi

ui_step 1 6 "Discover project manifests"

MANIFESTS=()
for f in "${MANIFEST_DIR}"/*.project.yaml; do
    [[ -f "$f" ]] || continue
    MANIFESTS+=("$f")
done

if (( ${#MANIFESTS[@]} == 0 )); then
    ui_error "No *.project.yaml files found in ${MANIFEST_DIR}"
    exit 1
fi

# Filter by BOARD_PROJECTS env var if set (space-separated project names)
# Falls back to DEVVM_PROJECTS for backwards compatibility
ACTIVE_PROJECTS="${BOARD_PROJECTS:-${DEVVM_PROJECTS:-}}"
if [[ -n "$ACTIVE_PROJECTS" ]]; then
    ui_info "Project filter active, filtering to: ${ACTIVE_PROJECTS}"
    FILTERED=()
    for manifest in "${MANIFESTS[@]}"; do
        proj_name=$(manifest_get "$manifest" ".name")
        for selected in $ACTIVE_PROJECTS; do
            if [[ "$proj_name" == "$selected" ]]; then
                FILTERED+=("$manifest")
                break
            fi
        done
    done
    MANIFESTS=("${FILTERED[@]}")

    if (( ${#MANIFESTS[@]} == 0 )); then
        ui_error "No manifests matched project filter: ${ACTIVE_PROJECTS}"
        exit 1
    fi
fi

for manifest in "${MANIFESTS[@]}"; do
    proj_name=$(manifest_get "$manifest" ".name")
    ui_success "Found: ${proj_name} ($(basename "$manifest"))"
done
ui_info "Total: ${#MANIFESTS[@]} project(s)"

# ── Step 2: Provision each project ──

ui_step 2 6 "Provision projects"

_PROJECT_NAMES=()
_PROJECT_STATUSES=()
PROVISIONED_MANIFESTS=()
ALL_WARNINGS=()
HAS_FATAL=false

ENGINE_FLAGS=()
$QUIET && ENGINE_FLAGS+=(--quiet)

for manifest in "${MANIFESTS[@]}"; do
    PROJECT_NAME=$(manifest_get "$manifest" ".name")
    ui_header "$PROJECT_NAME"

    _PROJECT_NAMES+=("$PROJECT_NAME")
    if bash "${SCRIPT_DIR}/provision-engine.sh" "$HOST" "$KEY_PATH" "$manifest" "$USER" "$KV_NAME" ${ENGINE_FLAGS[@]+"${ENGINE_FLAGS[@]}"}; then
        _PROJECT_STATUSES+=("success")
        PROVISIONED_MANIFESTS+=("$manifest")
        # Structured output for parent to parse in quiet mode
        $QUIET && echo "OK:$PROJECT_NAME"
    else
        _PROJECT_STATUSES+=("failed")
        HAS_FATAL=true
        ui_error "Provisioning failed for $PROJECT_NAME"
        $QUIET && echo "FAIL:$PROJECT_NAME"
    fi
done

# ── Step 3: Generate workspace file ──

ui_step 3 6 "Generate workspace file"

if (( ${#PROVISIONED_MANIFESTS[@]} > 0 )); then
    WORKSPACE_JSON=$(manifest_generate_workspace "${PROVISIONED_MANIFESTS[@]}")

    WORKSPACE_TMP=$(mktemp /tmp/board-workspace-XXXXXXXX)
    echo "$WORKSPACE_JSON" > "$WORKSPACE_TMP"

    _ssh "mkdir -p ~/projects" &>/dev/null || true
    _scp "$WORKSPACE_TMP" "$USER@$HOST:~/projects/board.code-workspace" &>/dev/null
    rm -f "$WORKSPACE_TMP"
    ui_success "Uploaded board.code-workspace"
else
    ui_warn "No projects provisioned successfully, skipping workspace file"
    ALL_WARNINGS+=("Workspace file not generated (no successful projects)")
fi

# ── Step 4: Generate check script ──

ui_step 4 6 "Generate health check script"

if (( ${#PROVISIONED_MANIFESTS[@]} > 0 )); then
    CHECK_SCRIPT=$(manifest_generate_check_script "${PROVISIONED_MANIFESTS[@]}")

    CHECK_TMP=$(mktemp /tmp/board-check-XXXXXXXX)
    echo "$CHECK_SCRIPT" > "$CHECK_TMP"

    _ssh "mkdir -p ~/projects/.board" &>/dev/null || true
    _scp "$CHECK_TMP" "$USER@$HOST:~/projects/.board/check.sh" &>/dev/null
    rm -f "$CHECK_TMP"
    _ssh "chmod +x ~/projects/.board/check.sh"
    ui_success "Uploaded check.sh"

    # Install alias in .bashrc
    _ssh "grep -q 'alias check=' ~/.bashrc || echo 'alias check=\"bash ~/projects/.board/check.sh\"' >> ~/.bashrc"
    ui_success "Installed 'check' alias in .bashrc"

    # Verify board-help is available
    _ssh "grep -q 'board-help' ~/.bashrc || echo 'board-help function not found in .bashrc — may need re-provisioning' >&2"
else
    ui_warn "No projects provisioned successfully, skipping check script"
    ALL_WARNINGS+=("Check script not generated (no successful projects)")
fi

# ── Step 5: Copy manifests to VM ──

ui_step 5 6 "Copy manifests to VM"

_ssh "mkdir -p ~/projects/.board/project-manifests" &>/dev/null || true

for manifest in "${MANIFESTS[@]}"; do
    _scp "$manifest" "$USER@$HOST:~/projects/.board/project-manifests/" &>/dev/null
    ui_success "Copied $(basename "$manifest")"
done

# ── Step 7: Summary ──

ui_step 6 6 "Summary"

ELAPSED=$(( SECONDS - START_TIME ))
ELAPSED_MIN=$(( ELAPSED / 60 ))
ELAPSED_SEC=$(( ELAPSED % 60 ))

SUMMARY_LINES=()
SUCCESS_COUNT=0
FAIL_COUNT=0

for i in "${!_PROJECT_NAMES[@]}"; do
    PROJECT_NAME="${_PROJECT_NAMES[$i]}"
    STATUS="${_PROJECT_STATUSES[$i]}"
    if [[ "$STATUS" == "success" ]]; then
        SUMMARY_LINES+=("$(printf '%-20s %s' "$PROJECT_NAME" "SUCCESS")")
        (( SUCCESS_COUNT++ ))
    else
        SUMMARY_LINES+=("$(printf '%-20s %s' "$PROJECT_NAME" "FAILED")")
        (( FAIL_COUNT++ ))
    fi
done

SUMMARY_LINES+=("")
SUMMARY_LINES+=("Total: ${#MANIFESTS[@]} project(s), ${SUCCESS_COUNT} succeeded, ${FAIL_COUNT} failed")
SUMMARY_LINES+=("Time: ${ELAPSED_MIN}m ${ELAPSED_SEC}s")

ui_summary_box "Provisioning Results" "${SUMMARY_LINES[@]}"

# Print any collected warnings
if (( ${#ALL_WARNINGS[@]} > 0 )) && ! $QUIET; then
    ui_header "Warnings"
    for warn in "${ALL_WARNINGS[@]}"; do
        ui_warn "$warn"
    done
    echo ""
fi

# Exit code: 0 if all succeeded, 1 if any had fatal errors
if $HAS_FATAL; then
    exit 1
fi
exit 0
