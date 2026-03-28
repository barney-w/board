#!/usr/bin/env bats

setup() {
    load 'test_helper/common'
}

# ── setup.sh tests ──

@test "setup.sh: _CLEANUP_FILES array is declared" {
    grep -q '_CLEANUP_FILES=()' "${PROJECT_ROOT}/scripts/setup.sh"
}

@test "setup.sh: EXIT trap calls cleanup function" {
    grep -qE "trap.*cleanup.*EXIT" "${PROJECT_ROOT}/scripts/setup.sh"
}

@test "setup.sh: cleanup_on_exit removes _CLEANUP_FILES entries" {
    # Verify the cleanup function iterates over _CLEANUP_FILES and calls rm -f
    grep -A5 'cleanup_on_exit()' "${PROJECT_ROOT}/scripts/setup.sh" | grep -q 'rm -f'
}

@test "setup.sh: DEPLOY_VARS_FILE mktemp registers in _CLEANUP_FILES" {
    local mktemp_line
    mktemp_line=$(grep -n 'DEPLOY_VARS_FILE=\$(mktemp' "${PROJECT_ROOT}/scripts/setup.sh" | head -1 | cut -d: -f1)
    [ -n "$mktemp_line" ] || fail "No DEPLOY_VARS_FILE mktemp found"
    local end_line=$((mktemp_line + 3))
    sed -n "${mktemp_line},${end_line}p" "${PROJECT_ROOT}/scripts/setup.sh" | grep -q '_CLEANUP_FILES.*DEPLOY_VARS_FILE'
}

@test "setup.sh: PROVISION_LOG mktemp registers in _CLEANUP_FILES" {
    local mktemp_line
    mktemp_line=$(grep -n 'PROVISION_LOG=\$(mktemp' "${PROJECT_ROOT}/scripts/setup.sh" | head -1 | cut -d: -f1)
    [ -n "$mktemp_line" ] || fail "No PROVISION_LOG mktemp found"
    local end_line=$((mktemp_line + 3))
    sed -n "${mktemp_line},${end_line}p" "${PROJECT_ROOT}/scripts/setup.sh" | grep -q '_CLEANUP_FILES.*PROVISION_LOG'
}

# ── provision-projects.sh tests ──

@test "provision-projects.sh: WORKSPACE_TMP is cleaned up after use" {
    grep -A10 'WORKSPACE_TMP=\$(mktemp' "${PROJECT_ROOT}/scripts/provision-projects.sh" | grep -q 'rm -f.*WORKSPACE_TMP\|rm -f "\$WORKSPACE_TMP"'
}

@test "provision-projects.sh: CHECK_TMP is cleaned up after use" {
    grep -A10 'CHECK_TMP=\$(mktemp' "${PROJECT_ROOT}/scripts/provision-projects.sh" | grep -q 'rm -f.*CHECK_TMP\|rm -f "\$CHECK_TMP"'
}

# ── provision-engine.sh tests ──

@test "provision-engine.sh: tmp_script is cleaned up after use" {
    grep -A70 'tmp_script=\$(mktemp' "${PROJECT_ROOT}/scripts/provision-engine.sh" | grep -q 'rm -f.*tmp_script\|rm -f "\$tmp_script"'
}
