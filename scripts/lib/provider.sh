#!/usr/bin/env bash
# Provider interface — dispatches to cloud-specific implementations
# Set BOARD_PROVIDER=azure (default) or aws, gcp

BOARD_PROVIDER="${BOARD_PROVIDER:-azure}"

_PROVIDER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source the active provider implementation
case "$BOARD_PROVIDER" in
    azure)
        # shellcheck source=provider-azure.sh
        source "${_PROVIDER_DIR}/provider-azure.sh"
        ;;
    *)
        echo "Error: Unknown provider '$BOARD_PROVIDER'. Supported: azure" >&2
        exit 1
        ;;
esac

# ── Provider Interface ──
# These functions dispatch to _provider_<name>_<function> implementations.
# To add a new provider, create scripts/lib/provider-<name>.sh implementing
# each _provider_<name>_* function below.

provider_login() {
    "_provider_${BOARD_PROVIDER}_login" "$@"
}

provider_deploy() {
    "_provider_${BOARD_PROVIDER}_deploy" "$@"
}

provider_start_vm() {
    "_provider_${BOARD_PROVIDER}_start_vm" "$@"
}

provider_stop_vm() {
    "_provider_${BOARD_PROVIDER}_stop_vm" "$@"
}

provider_get_status() {
    "_provider_${BOARD_PROVIDER}_get_status" "$@"
}

provider_list_vms() {
    "_provider_${BOARD_PROVIDER}_list_vms" "$@"
}

provider_delete_vm() {
    "_provider_${BOARD_PROVIDER}_delete_vm" "$@"
}

provider_wait_ready() {
    "_provider_${BOARD_PROVIDER}_wait_ready" "$@"
}

provider_get_ip() {
    "_provider_${BOARD_PROVIDER}_get_ip" "$@"
}
