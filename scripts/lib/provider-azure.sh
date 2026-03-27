#!/usr/bin/env bash
# Azure provider implementation for Board
# Wraps existing azure.sh functions in the provider interface

_AZURE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=azure.sh
source "${_AZURE_DIR}/azure.sh"

# ── Provider Interface Implementation ──

_provider_azure_login() {
    ensure_az_login "$@"
}

_provider_azure_deploy() {
    deploy_vm "$@"
}

_provider_azure_start_vm() {
    local name="$1"
    local env="${2:-personal}"
    local region="${3:-aue}"
    az vm start \
        --resource-group "rg-${env}-${region}-devvm" \
        --name "vm-${env}-${region}-devvm-${name}" \
        --no-wait
}

_provider_azure_stop_vm() {
    local name="$1"
    local env="${2:-personal}"
    local region="${3:-aue}"
    az vm deallocate \
        --resource-group "rg-${env}-${region}-devvm" \
        --name "vm-${env}-${region}-devvm-${name}" \
        --no-wait
}

_provider_azure_get_status() {
    local name="$1"
    local env="${2:-personal}"
    local region="${3:-aue}"
    az vm get-instance-view \
        --resource-group "rg-${env}-${region}-devvm" \
        --name "vm-${env}-${region}-devvm-${name}" \
        --query 'instanceView.statuses[1].displayStatus' \
        -o tsv 2>/dev/null || echo "unknown"
}

_provider_azure_list_vms() {
    local env="${1:-personal}"
    local region="${2:-aue}"
    az vm list \
        --resource-group "rg-${env}-${region}-devvm" \
        --show-details \
        --query '[].{name:name, status:powerState, ip:publicIps, size:hardwareProfile.vmSize}' \
        -o tsv 2>/dev/null
}

_provider_azure_delete_vm() {
    local name="$1"
    local env="${2:-personal}"
    local region="${3:-aue}"
    az vm delete \
        --resource-group "rg-${env}-${region}-devvm" \
        --name "vm-${env}-${region}-devvm-${name}" \
        --force-deletion true \
        --yes
}

_provider_azure_wait_ready() {
    wait_for_cloud_init "$@"
}

_provider_azure_get_ip() {
    local name="$1"
    local env="${2:-personal}"
    local region="${3:-aue}"
    az vm show \
        --resource-group "rg-${env}-${region}-devvm" \
        --name "vm-${env}-${region}-devvm-${name}" \
        --show-details \
        --query 'publicIps' -o tsv 2>/dev/null
}
