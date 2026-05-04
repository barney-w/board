# shellcheck shell=bash
# Shared SSH helpers for board recipes. Source, don't execute.
#
# Usage:
#   source cli/scripts/board-ssh.sh
#   _board_ssh_setup myvm           # populates BOARD_SSH_ARGS / BOARD_SSH_TARGET / BOARD_SSH_HOST
#   ssh "${BOARD_SSH_ARGS[@]}" "$BOARD_SSH_TARGET" "echo hi"
#
#   board_forward_ports myvm        # foreground: discover + tunnel every listening port

: "${BOARD_LOCATION:=australiaeast}"

_board_ssh_setup() {
    local name=$1
    BOARD_SSH_HOST="devvm-${name}.${BOARD_LOCATION}.cloudapp.azure.com"
    local key="$HOME/.ssh/devvm-${name}"
    if [ -f "$key" ]; then
        BOARD_SSH_ARGS=(-i "$key")
        BOARD_SSH_TARGET="devuser@$BOARD_SSH_HOST"
        return 0
    fi
    local cert_dir="$HOME/.ssh/board-entra/devvm-${name}"
    if [ -f "$cert_dir/id_rsa" ]; then
        BOARD_SSH_ARGS=(-i "$cert_dir/id_rsa" -o "CertificateFile=$cert_dir/id_rsa.pub-aadcert.pub")
        BOARD_SSH_TARGET="$BOARD_SSH_HOST"
        return 0
    fi
    echo "ERROR: No SSH key or Entra certificate found for devvm-${name}." >&2
    echo "Run: just ssh-config-write ${name}" >&2
    return 1
}

# Ports that are TCP services but not HTTP — exclude from the "open in browser" list.
_board_is_infra_port() {
    case "$1" in
        5432|3306|6379|27017|1433|5984|9200|5672|15672|4369) return 0 ;;
        *) return 1 ;;
    esac
}

# Discover every listening TCP port on the VM and forward each to the same
# port on localhost. Foregrounds the SSH tunnel; Ctrl+C closes it.
board_forward_ports() {
    _board_ssh_setup "$1" || return 1
    echo "Discovering listening ports on $BOARD_SSH_HOST..."
    local ports
    ports=$(ssh "${BOARD_SSH_ARGS[@]}" "$BOARD_SSH_TARGET" \
        "ss -tlnH 2>/dev/null | awk '{print \$4}' | grep -oP '(?:127\.0\.0\.1|0\.0\.0\.0|\[::\]|localhost):?\K\d+' | sort -un | awk '\$1 <= 32767 && \$1 != 22'")
    if [ -z "$ports" ]; then
        echo "No services listening on the VM."
        return 0
    fi
    local forwards=() skipped=() web_ports=()
    echo "Forwarding ports:"
    while IFS= read -r port; do
        if lsof -iTCP:"$port" -sTCP:LISTEN -P -n >/dev/null 2>&1; then
            skipped+=("$port")
        else
            echo "  localhost:$port → VM:$port"
            forwards+=(-L "$port:localhost:$port")
            if ! _board_is_infra_port "$port"; then
                web_ports+=("$port")
            fi
        fi
    done <<<"$ports"
    if [ "${#skipped[@]}" -gt 0 ]; then
        echo "  (skipped, already in use locally: ${skipped[*]})"
    fi
    if [ "${#forwards[@]}" -eq 0 ]; then
        echo "All ports already forwarded (likely by VS Code)."
        return 0
    fi
    if [ "${#web_ports[@]}" -gt 0 ]; then
        echo
        echo "Open in your browser:"
        for p in "${web_ports[@]}"; do
            echo "  http://localhost:${p}"
        done
        echo
        echo "  VS Code users: the Ports tab shows these automatically — no manual forwarding needed."
    fi
    echo
    echo "Press Ctrl+C to close all tunnels."
    ssh "${BOARD_SSH_ARGS[@]}" "${forwards[@]}" -N "$BOARD_SSH_TARGET"
}
