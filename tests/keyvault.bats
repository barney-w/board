#!/usr/bin/env bats

setup() {
    load 'test_helper/common'
    load 'test_helper/az-mock'
    source "${PROJECT_ROOT}/scripts/lib/ui.sh"
    USE_GUM=false
    export BOARD_KV_RETRY_DELAY=0
    source "${PROJECT_ROOT}/scripts/lib/keyvault.sh"
}

@test "create_keyvault: vault already exists — returns success without creating" {
    AZ_MOCK_KV_STATE=exists
    run create_keyvault "kv-test" "rg-test" "australiaeast"
    assert_success
    assert_output --partial "already exists"
}

@test "create_keyvault: soft-deleted vault — recovers it" {
    AZ_MOCK_KV_STATE=soft-deleted
    AZ_MOCK_KV_RECOVER_FAILS=false
    run create_keyvault "kv-test" "rg-test" "australiaeast"
    assert_success
    assert_output --partial "recovered"
}

@test "create_keyvault: soft-deleted vault, recovery fails — shows error" {
    AZ_MOCK_KV_STATE=soft-deleted
    AZ_MOCK_KV_RECOVER_FAILS=true
    run create_keyvault "kv-test" "rg-test" "australiaeast"
    assert_failure
}

@test "create_keyvault: no vault at all — creates fresh" {
    AZ_MOCK_KV_STATE=absent
    run create_keyvault "kv-test" "rg-test" "australiaeast"
    assert_success
    assert_output --partial "created"
}

@test "create_keyvault: create fails with ConflictError — retries with purge" {
    AZ_MOCK_KV_STATE=absent
    AZ_MOCK_KV_CREATE_CONFLICT=true
    run create_keyvault "kv-test" "rg-test" "australiaeast"
    assert_success
    assert_output --partial "created"
}
