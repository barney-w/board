#!/usr/bin/env bats

setup() {
    load 'test_helper/common'
    USE_GUM=false
    source "${PROJECT_ROOT}/scripts/lib/ui.sh"
}

@test "ui_success prints message" {
    run ui_success "test message"
    assert_output --partial "test message"
}

@test "ui_error prints message" {
    run ui_error "error msg"
    assert_output --partial "error msg"
}

@test "ui_info prints message" {
    run ui_info "info msg"
    assert_output --partial "info msg"
}

@test "ui_warn prints message" {
    run ui_warn "warn msg"
    assert_output --partial "warn msg"
}

@test "ui_header prints bordered text" {
    run ui_header "Test Header"
    assert_output --partial "Test Header"
}

@test "ui_step prints step number" {
    run ui_step 1 5 "Deploy"
    assert_output --partial "1"
    assert_output --partial "Deploy"
}
