#!/usr/bin/env bash
# Prerequisite validation for Board setup

check_command() {
    local name="$1"
    local cmd="$2"
    local install_hint="$3"
    local required="${4:-true}"

    if command -v "$cmd" &>/dev/null; then
        local version
        version=$("$cmd" --version 2>&1 | head -1) || version="installed"
        ui_success "$name ($version)"
        return 0
    else
        if [[ "$required" == "true" ]]; then
            ui_error "$name not found — install with: $install_hint"
        else
            ui_warn "$name not found (optional) — install with: $install_hint"
        fi
        return 1
    fi
}

install_gum() {
    if command -v brew &>/dev/null; then
        ui_info "Installing gum via Homebrew..."
        brew install gum >/dev/null 2>&1
    elif command -v choco &>/dev/null; then
        ui_info "Installing gum via Chocolatey..."
        choco install gum -y >/dev/null 2>&1
    elif command -v scoop &>/dev/null; then
        ui_info "Installing gum via Scoop..."
        scoop install charm-gum >/dev/null 2>&1
    elif command -v winget &>/dev/null; then
        ui_info "Installing gum via winget..."
        winget install charmbracelet.gum --accept-source-agreements --accept-package-agreements >/dev/null 2>&1
    else
        return 1
    fi
    command -v gum &>/dev/null
}

check_prerequisites() {
    local failed=0

    check_command "Azure CLI"  az      "brew install azure-cli"    true  || ((failed++))
    check_command "just"       just    "brew install just"         true  || ((failed++))
    check_command "ssh-keygen" ssh-keygen "included with macOS"    true  || ((failed++))
    check_command "ssh"        ssh     "included with macOS"       true  || ((failed++))

    if ! command -v gum &>/dev/null; then
        ui_info "gum not found — attempting to install..."
        if install_gum; then
            ui_success "gum installed"
            # shellcheck disable=SC2034 # used by sourced ui.sh
            USE_GUM=true
        else
            ui_warn "Could not auto-install gum. Install manually: https://github.com/charmbracelet/gum#installation"
            ui_info "Continuing without gum (reduced UI experience)"
        fi
    else
        check_command "gum" gum "" true
    fi

    if (( failed > 0 )); then
        echo ""
        ui_error "Missing $failed required tool(s). Install them and re-run 'just board'."
        return 1
    fi
    return 0
}
