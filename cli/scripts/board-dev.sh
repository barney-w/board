#!/usr/bin/env bash
# board-dev — start/stop/attach a project's dev workflow on a board VM.
#
# Reads dev.run from projects/<project>.project.yaml on the laptop, runs it
# inside a detached tmux session named "proj-<project>" on the VM, and
# forwards every listening port back to localhost.
#
# Manual control: nothing auto-starts on VM boot.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=cli/scripts/board-ssh.sh
source "$SCRIPT_DIR/board-ssh.sh"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

usage() {
    cat >&2 <<EOF
Usage:
  board-dev start <vm> <project>   Start project's dev.run on the VM, then forward ports.
  board-dev stop  <vm> <project>   Kill the project's tmux session on the VM.
  board-dev logs  <vm> <project>   Attach to the project's tmux session (Ctrl+B d to detach).
  board-dev list  <vm>             List running project sessions on the VM.
EOF
    exit 2
}

require_yq() {
    command -v yq >/dev/null 2>&1 || die "yq is required but not installed (brew install yq)."
}

# Locate projects/ relative to cwd, then walk up.
find_manifest_dir() {
    local dir
    dir=$(pwd)
    while [ "$dir" != "/" ]; do
        if [ -d "$dir/projects" ] && ls "$dir/projects"/*.project.yaml >/dev/null 2>&1; then
            echo "$dir/projects"
            return 0
        fi
        dir=$(dirname "$dir")
    done
    die "No projects/ directory with manifests found from $(pwd) upward."
}

read_manifest() {
    # Sets MANIFEST, DEV_RUN, PROJECT_PATH from the project name.
    local proj=$1
    local manifest_dir
    manifest_dir=$(find_manifest_dir)
    MANIFEST="$manifest_dir/${proj}.project.yaml"
    [ -f "$MANIFEST" ] || die "Manifest not found: $MANIFEST"

    DEV_RUN=$(yq eval '.dev.run // ""' "$MANIFEST")
    [ -n "$DEV_RUN" ] || die "$MANIFEST has no .dev.run — nothing to start."

    PROJECT_PATH=$(yq eval '.path // ("~/projects/" + .name)' "$MANIFEST")
}

cmd_start() {
    local vm=$1 proj=$2
    read_manifest "$proj"
    _board_ssh_setup "$vm" || exit 1

    local session="proj-${proj}"

    # Heredoc without quoted sentinel: ${PROJECT_PATH} and ${DEV_RUN} are
    # expanded locally; the remote bash then expands ~ in cd / -c.
    # shellcheck disable=SC2087
    ssh "${BOARD_SSH_ARGS[@]}" "$BOARD_SSH_TARGET" bash -s <<EOF
set -e
SESSION='${session}'
if tmux has-session -t "\$SESSION" 2>/dev/null; then
    echo "Already running (tmux session \$SESSION)."
else
    if ! cd ${PROJECT_PATH} 2>/dev/null; then
        echo "ERROR: ${PROJECT_PATH} not found on the VM." >&2
        echo "Run: just install-projects ${vm}" >&2
        exit 1
    fi
    tmux new-session -d -s "\$SESSION" -c ${PROJECT_PATH} '${DEV_RUN}; echo; echo "[${proj} exited — Ctrl+B d to detach, or restart with the same command]"; exec bash'
    echo "Started: ${DEV_RUN}"
    echo "  tmux session: \$SESSION   (just dev-logs ${vm} ${proj} to attach)"
fi
EOF

    echo
    board_forward_ports "$vm"
}

cmd_stop() {
    local vm=$1 proj=$2
    _board_ssh_setup "$vm" || exit 1
    local session="proj-${proj}"
    # shellcheck disable=SC2029
    ssh "${BOARD_SSH_ARGS[@]}" "$BOARD_SSH_TARGET" \
        "tmux kill-session -t '${session}' 2>/dev/null && echo 'Stopped ${session}.' || echo '${session} was not running.'"
}

cmd_logs() {
    local vm=$1 proj=$2
    _board_ssh_setup "$vm" || exit 1
    local session="proj-${proj}"
    # -t for TTY (required by tmux attach)
    # shellcheck disable=SC2029
    ssh -t "${BOARD_SSH_ARGS[@]}" "$BOARD_SSH_TARGET" "tmux attach -t '${session}'"
}

cmd_list() {
    local vm=$1
    _board_ssh_setup "$vm" || exit 1
    ssh "${BOARD_SSH_ARGS[@]}" "$BOARD_SSH_TARGET" \
        "tmux list-sessions -F '#{session_name}  (#{session_windows} window, created #{t:session_created})' 2>/dev/null | grep '^proj-' || echo 'No project sessions running.'"
}

[ $# -ge 1 ] || usage
action=$1
shift || true

case "$action" in
    start)
        [ $# -eq 2 ] || usage
        require_yq
        cmd_start "$1" "$2"
        ;;
    stop)
        [ $# -eq 2 ] || usage
        cmd_stop "$1" "$2"
        ;;
    logs)
        [ $# -eq 2 ] || usage
        cmd_logs "$1" "$2"
        ;;
    list)
        [ $# -eq 1 ] || usage
        cmd_list "$1"
        ;;
    *)
        usage
        ;;
esac
