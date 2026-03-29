#!/usr/bin/env bats

setup() {
    load 'test_helper/common'
    load 'test_helper/az-mock'
    source "${PROJECT_ROOT}/scripts/lib/ui.sh"
    USE_GUM=false
    export BOARD_KV_RETRY_DELAY=0
    source "${PROJECT_ROOT}/scripts/lib/keyvault.sh"
}

@test "create after destroy: handles KV in soft-deleted state" {
    AZ_MOCK_KV_STATE=soft-deleted
    AZ_MOCK_KV_RECOVER_FAILS=false
    run create_keyvault "kv-test" "rg-test" "australiaeast"
    assert_success
}

@test "create after destroy: ConflictError triggers retry with purge" {
    AZ_MOCK_KV_STATE=absent
    AZ_MOCK_KV_CREATE_CONFLICT=true
    run create_keyvault "kv-test" "rg-test" "australiaeast"
    assert_success
}
