#!/usr/bin/env bats

setup() {
    load 'test_helper/common'
}

@test "setup.sh checks VSCODE_CLI_AVAILABLE before tunnel setup" {
    # Verify the guard: VSCODE_CLI_AVAILABLE defaults to false and is checked before tunnel work
    grep -q 'VSCODE_CLI_AVAILABLE=false' "${PROJECT_ROOT}/scripts/setup.sh"
    grep -q 'if \$VSCODE_CLI_AVAILABLE' "${PROJECT_ROOT}/scripts/setup.sh"
}

@test "setup.sh sets VSCODE_CLI_AVAILABLE via SSH test" {
    # Verify the check uses test -x /usr/local/bin/code over SSH
    grep -q 'test -x /usr/local/bin/code' "${PROJECT_ROOT}/scripts/setup.sh"
}

@test "setup.sh warns when VS Code CLI unavailable" {
    grep -q 'VS Code CLI not installed' "${PROJECT_ROOT}/scripts/setup.sh"
}

@test "justfile tunnel-setup checks CLI before attempting tunnel" {
    # The tunnel-setup recipe should check for the binary before proceeding
    grep -A15 'tunnel-setup' "${PROJECT_ROOT}/justfile" | grep -q 'test -x /usr/local/bin/code'
}

@test "cloud-init VS Code CLI install is non-fatal" {
    # The cloud-init YAML should have a fallback/warning for VS Code CLI install failure
    grep -q '|| {' "${PROJECT_ROOT}/infra/cloud-init/cloud-init.yaml"
    grep -q 'VS Code CLI install failed (non-fatal)' "${PROJECT_ROOT}/infra/cloud-init/cloud-init.yaml"
}

@test "setup.sh: hostname set AFTER login and BEFORE service install" {
    local setup="${PROJECT_ROOT}/scripts/setup.sh"
    local login_line hostname_line install_line
    login_line=$(grep -n 'code tunnel user login' "$setup" | head -1 | cut -d: -f1)
    hostname_line=$(grep -n 'hostnamectl set-hostname' "$setup" | head -1 | cut -d: -f1)
    install_line=$(grep -n 'code tunnel service install' "$setup" | head -1 | cut -d: -f1)
    [ -n "$login_line" ]
    [ -n "$hostname_line" ]
    [ -n "$install_line" ]
    [ "$hostname_line" -gt "$login_line" ]
    [ "$install_line" -gt "$hostname_line" ]
}

@test "justfile: hostname set AFTER login and BEFORE service install" {
    local jf="${PROJECT_ROOT}/justfile"
    local login_line hostname_line install_line
    login_line=$(grep -n 'code tunnel user login' "$jf" | head -1 | cut -d: -f1)
    hostname_line=$(grep -n 'hostnamectl set-hostname' "$jf" | head -1 | cut -d: -f1)
    install_line=$(grep -n 'code tunnel service install' "$jf" | head -1 | cut -d: -f1)
    [ -n "$login_line" ]
    [ -n "$hostname_line" ]
    [ -n "$install_line" ]
    [ "$hostname_line" -gt "$login_line" ]
    [ "$install_line" -gt "$hostname_line" ]
}

@test "setup.sh: does NOT use code tunnel rename (unreliable on fresh VMs)" {
    ! grep -q 'code tunnel rename' "${PROJECT_ROOT}/scripts/setup.sh"
}

@test "justfile: does NOT use code tunnel rename (unreliable on fresh VMs)" {
    ! grep -q 'code tunnel rename' "${PROJECT_ROOT}/justfile"
}

@test "setup.sh: tunnel service uninstall before reinstall (handles re-runs)" {
    grep -q 'tunnel service uninstall' "${PROJECT_ROOT}/scripts/setup.sh"
}

@test "cloud-init sets hostname via __BOARD_HOSTNAME__ placeholder" {
    grep -q 'hostname: __BOARD_HOSTNAME__' "${PROJECT_ROOT}/infra/cloud-init/cloud-init.yaml"
}

@test "Bicep replaces __BOARD_HOSTNAME__ with devvm-developerName" {
    grep -q "__BOARD_HOSTNAME__" "${PROJECT_ROOT}/infra/main.bicep"
    grep -q "devvm-" "${PROJECT_ROOT}/infra/main.bicep"
}

@test "export-bundle.sh uses --rawfile for SSH keys (preserves trailing newline)" {
    grep -q '\-\-rawfile privKey' "${PROJECT_ROOT}/scripts/export-bundle.sh"
    grep -q '\-\-rawfile pubKey' "${PROJECT_ROOT}/scripts/export-bundle.sh"
    # Must NOT use --arg for key content
    ! grep -q '\-\-arg privKey' "${PROJECT_ROOT}/scripts/export-bundle.sh"
    ! grep -q '\-\-arg pubKey' "${PROJECT_ROOT}/scripts/export-bundle.sh"
}
