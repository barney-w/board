# ── Board Recipes ──

set dotenv-load := true

# Python CLI invocation
_board := "uv run --project cli board"

# Defaults (overridable via env or CLI)
default_env := "personal"
default_sku := "Standard_D2s_v6"
default_location := "australiaeast"
default_region := "aue"

# ── Interactive Setup ──

# Board up — onboard a developer by provisioning a cloud dev environment
board *args="":
    @{{_board}} up {{args}}

# Record a demo of the board wizard (no Azure credentials needed)
demo:
    @{{_board}} up --demo

# Shape — shaper's control panel (manage boards, projects, and secrets)
shape:
    @{{_board}} shape

# ── Deployment ──

# Deploy a new board (direct Bicep deploy, no wizard)
create-vm name env=default_env sku=default_sku:
    @{{_board}} create-vm {{name}} --env {{env}} --sku {{sku}} --location {{default_location}} --region-short {{default_region}}

# Create the resource group (run once per environment)
create-rg env=default_env:
    @{{_board}} create-rg --env {{env}} --location {{default_location}} --region-short {{default_region}}

# Validate Bicep without deploying
validate env=default_env:
    @{{_board}} validate --env {{env}} --region-short {{default_region}}

# Preview what would change
what-if name env=default_env:
    @{{_board}} what-if {{name}} --env {{env}} --region-short {{default_region}}

# ── VM Operations ──

# Start a board
start name env=default_env:
    @{{_board}} vm start {{name}} --env {{env}}

# Stop (deallocate) a board
stop name env=default_env:
    @{{_board}} vm stop {{name}} --env {{env}}

# SSH into a board
ssh name:
    @{{_board}} vm ssh {{name}}

# SSH via Entra ID (work tenant)
ssh-entra name env=default_env:
    az ssh vm \
        --resource-group rg-{{env}}-{{default_region}}-devvm \
        --name vm-{{env}}-{{default_region}}-devvm-{{name}}

# Show board status
status name env=default_env:
    @{{_board}} vm status {{name}} --env {{env}}

# List all boards and their status
list env=default_env:
    @{{_board}} vm ls --env {{env}}

# ── Teardown ──

# Delete a single board and all associated resources
delete-vm name env=default_env confirm="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "{{confirm}}" == "yes" ]]; then
        {{_board}} vm delete {{name}} --env {{env}} --yes
    else
        {{_board}} vm delete {{name}} --env {{env}}
    fi

# Delete entire environment (nuclear option, pass confirm=yes to skip prompt)
destroy-all env=default_env confirm="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "{{confirm}}" == "yes" ]]; then
        {{_board}} destroy --env {{env}} --region-short {{default_region}} --yes
    else
        {{_board}} destroy --env {{env}} --region-short {{default_region}}
    fi

# ── Utilities ──

# Generate an SSH keypair for a dev
generate-key name:
    @{{_board}} vm keygen {{name}}

# Run smoke tests against a deployed board
smoke-test name:
    @{{_board}} smoke-test {{name}}

# Check cloud-init status on a board
cloud-init-status name:
    ssh -i ~/.ssh/devvm-{{name}} -o StrictHostKeyChecking=accept-new \
        devuser@devvm-{{name}}.{{default_location}}.cloudapp.azure.com \
        'cloud-init status --long && test -f ~/.cloud-init-complete && echo "Bootstrap: COMPLETE" || echo "Bootstrap: IN PROGRESS"'

# ── Developer Experience ──

# Print SSH config block for a developer's local machine
ssh-config name:
    @{{_board}} ssh-config show {{name}}

# Generate SSH config for Entra ID auth (work tenant)
ssh-config-entra name env=default_env:
    @echo "# Add this to ~/.ssh/config"
    @echo ""
    @echo "Host devvm-{{name}}"
    @echo "    HostName devvm-{{name}}.{{default_location}}.cloudapp.azure.com"
    @echo "    ProxyCommand az ssh proxy --resource-group rg-{{env}}-{{default_region}}-devvm --vm-name vm-{{env}}-{{default_region}}-devvm-{{name}} --port %p"
    @echo "    ForwardAgent yes"
    @echo "    ServerAliveInterval 60"
    @echo "    ServerAliveCountMax 3"
    @echo "    LocalForward 8080 127.0.0.1:8080"
    @echo "    LocalForward 9091 127.0.0.1:9190"
    @echo "    LocalForward 9444 127.0.0.1:9443"
    @echo ""
    @echo "# Usage:  ssh devvm-{{name}}"

# First-time setup wizard (run on the board after first SSH login)
setup-me name:
    ssh -i ~/.ssh/devvm-{{name}} devuser@devvm-{{name}}.{{default_location}}.cloudapp.azure.com 'bash ~/setup-me.sh'

# Access Cockpit system admin UI via SSH tunnel (localhost:9091 → VM:9190)
cockpit name:
    @echo "Opening SSH tunnel to Cockpit..."
    @echo "Open http://localhost:9091 in your browser."
    @echo "Log in with devuser / board."
    @echo ""
    @echo "Press Ctrl+C to close the tunnel."
    ssh -L 9091:localhost:9190 -N -i ~/.ssh/devvm-{{name}} devuser@devvm-{{name}}.{{default_location}}.cloudapp.azure.com

# Access Portainer Docker management UI via SSH tunnel (localhost:9444 → VM:9443)
portainer name:
    @echo "Opening SSH tunnel to Portainer..."
    @echo "Open https://localhost:9444 in your browser."
    @echo "Accept the self-signed certificate warning. Default admin password: boardboard12"
    @echo ""
    @echo "Press Ctrl+C to close the tunnel."
    ssh -L 9444:localhost:9443 -N -i ~/.ssh/devvm-{{name}} devuser@devvm-{{name}}.{{default_location}}.cloudapp.azure.com

# Access code-server via SSH tunnel (opens browser IDE at localhost:8080)
code-server name:
    @echo "Opening SSH tunnel to code-server..."
    @echo "Open http://localhost:8080 in your browser."
    @PASS=$(ssh -i ~/.ssh/devvm-{{name}} devuser@devvm-{{name}}.{{default_location}}.cloudapp.azure.com \
        'cat ~/.board/code-server-password 2>/dev/null || echo "unknown"') && \
        echo "Password: $PASS"
    @echo ""
    @echo "Press Ctrl+C to close the tunnel."
    ssh -L 8080:localhost:8080 -N -i ~/.ssh/devvm-{{name}} devuser@devvm-{{name}}.{{default_location}}.cloudapp.azure.com

# Forward all listening ports from a VM to localhost (dynamic discovery)
tunnel-all name:
    #!/usr/bin/env bash
    set -euo pipefail
    KEY=~/.ssh/devvm-{{name}}
    HOST="devvm-{{name}}.{{default_location}}.cloudapp.azure.com"
    echo "Discovering listening ports on $HOST..."
    PORTS=$(ssh -i "$KEY" devuser@"$HOST" \
        "ss -tlnH 2>/dev/null | awk '{print \$4}' | grep -oP '(?:127\.0\.0\.1|0\.0\.0\.0|\[::\]|localhost):?\K\d+' | sort -un | awk '\$1 <= 32767 && \$1 != 22'")
    if [ -z "$PORTS" ]; then
        echo "No services listening on the VM."
        exit 0
    fi
    FORWARDS=""
    SKIPPED=""
    echo "Forwarding ports:"
    while IFS= read -r port; do
        if lsof -iTCP:"$port" -sTCP:LISTEN -P -n >/dev/null 2>&1; then
            SKIPPED="$SKIPPED $port"
        else
            echo "  localhost:$port → VM:$port"
            FORWARDS="$FORWARDS -L $port:localhost:$port"
        fi
    done <<< "$PORTS"
    if [ -n "$SKIPPED" ]; then
        echo "  (skipped, already in use locally:$SKIPPED)"
    fi
    if [ -z "$FORWARDS" ]; then
        echo "All ports already forwarded (likely by VS Code)."
        exit 0
    fi
    echo ""
    echo "Press Ctrl+C to close all tunnels."
    ssh $FORWARDS -N -i "$KEY" devuser@"$HOST"

# Set up VS Code Tunnel on a board (interactive GitHub auth)
tunnel-setup name:
    #!/usr/bin/env bash
    set -euo pipefail
    HOST="devvm-{{name}}.{{default_location}}.cloudapp.azure.com"
    KEY="$HOME/.ssh/devvm-{{name}}"
    echo "Setting up VS Code Tunnel on devvm-{{name}}..."
    if ! ssh -i "$KEY" -o ConnectTimeout=5 -o BatchMode=yes "devuser@${HOST}" \
        "test -x /usr/local/bin/code" 2>/dev/null; then
        echo "ERROR: VS Code CLI not installed on devvm-{{name}}."
        exit 1
    fi
    ssh -t -i "$KEY" "devuser@${HOST}" \
        '/usr/local/bin/code tunnel user login --provider github'
    ssh -i "$KEY" "devuser@${HOST}" \
        'sudo hostnamectl set-hostname "devvm-{{name}}"' || true
    ssh -i "$KEY" "devuser@${HOST}" \
        '/usr/local/bin/code tunnel service uninstall 2>/dev/null; true'
    ssh -i "$KEY" "devuser@${HOST}" \
        '/usr/local/bin/code tunnel service install --accept-server-license-terms && echo "https://vscode.dev/tunnel/devvm-{{name}}" > ~/.board/tunnel-url'
    echo ""
    echo "Tunnel ready: https://vscode.dev/tunnel/devvm-{{name}}"

# Open VS Code Tunnel in browser
tunnel-web name:
    @open "https://vscode.dev/tunnel/devvm-{{name}}" 2>/dev/null || \
        xdg-open "https://vscode.dev/tunnel/devvm-{{name}}" 2>/dev/null || \
        echo "Open in browser: https://vscode.dev/tunnel/devvm-{{name}}"

# Open a browser IDE for a board (interactive menu)
browser-ide name:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v gum &>/dev/null; then
        CHOICE=$(gum choose "VS Code Tunnel (full marketplace, Copilot)" "code-server (self-hosted, SSH tunnel)")
    else
        echo "1) VS Code Tunnel (full marketplace, Copilot)"
        echo "2) code-server (self-hosted, SSH tunnel)"
        read -p "Choose [1-2]: " num
        case "$num" in
            1) CHOICE="VS Code Tunnel" ;;
            *) CHOICE="code-server" ;;
        esac
    fi
    case "$CHOICE" in
        *"Tunnel"*)
            just tunnel-web {{name}}
            ;;
        *"code-server"*)
            just code-server {{name}}
            ;;
    esac

# Grant Entra ID SSH access to a developer (work tenant)
grant-ssh-access name email env=default_env:
    az role assignment create \
        --assignee "{{email}}" \
        --role "Virtual Machine Administrator Login" \
        --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/rg-{{env}}-{{default_region}}-devvm/providers/Microsoft.Compute/virtualMachines/vm-{{env}}-{{default_region}}-devvm-{{name}}"
    @echo "{{name}} can now SSH via: az ssh vm --resource-group rg-{{env}}-{{default_region}}-devvm --name vm-{{env}}-{{default_region}}-devvm-{{name}}"

# Build the VS Code extension (.vsix)
build-extension:
    cd extension && npm run build:prod && npx @vscode/vsce package --no-dependencies

# Create a starter kit (board pass + extension + setup scripts) for a developer
export-pass name env=default_env:
    @{{_board}} export-pass {{name}} --env {{env}} --region {{default_location}} --region-short {{default_region}}

# ── Project Operations ──

# Install projects on a board from manifest files
install-projects name keyvault="":
    #!/usr/bin/env bash
    set -euo pipefail
    CMD="{{_board}} install-projects {{name}}"
    [[ -n "{{keyvault}}" ]] && CMD="$CMD --keyvault {{keyvault}}"
    $CMD

# Check project service health on a board
project-status name:
    @{{_board}} project-status {{name}}

# ── Fleet Operations ──

# Show status of all boards in an environment
fleet-status env=default_env:
    @{{_board}} fleet --env {{env}}

# Auto-detect project stack and generate a manifest
init:
    @{{_board}} init

# ── Automation ──

# Write SSH config block directly to ~/.ssh/config (idempotent, managed markers)
ssh-config-write name:
    @{{_board}} ssh-config write {{name}}

# Remove SSH config block for a board
ssh-config-remove name:
    @{{_board}} ssh-config remove {{name}}

# Wait for cloud-init to complete on a board (polls with progress)
wait-ready name:
    @{{_board}} wait-ready {{name}}

# Preflight checks before deploying a board
preflight name env=default_env sku=default_sku:
    @{{_board}} preflight {{name}} --env {{env}} --sku {{sku}} --location {{default_location}} --region-short {{default_region}}

# Provision a board from zero to ready (one command does everything)
provision name env=default_env sku=default_sku:
    BOARD_NON_INTERACTIVE=1 BOARD_DEV_NAME={{name}} BOARD_ENVIRONMENT={{env}} BOARD_VM_SKU={{sku}} {{_board}} up --non-interactive

# Rotate SSH key for a board (invalidates existing board passes)
rotate-key name:
    @{{_board}} rotate-key {{name}}

# ── Static Analysis ──

# Lint Python code with ruff
lint-python:
    cd cli && uv run ruff check src/ tests/

# Format Python code with ruff
format-python:
    cd cli && uv run ruff format src/ tests/

# Build and lint Bicep templates
lint-bicep:
    az bicep build --file infra/main.bicep --stdout > /dev/null
    az bicep lint --file infra/main.bicep

# Validate cloud-init YAML schema
lint-cloud-init:
    cloud-init schema --config-file infra/cloud-init/cloud-init.yaml

# Validate project manifest YAML syntax
lint-manifests:
    @for f in projects/*.project.yaml projects/examples/*.project.yaml; do \
        [ -f "$$f" ] || continue; \
        yq eval '.' "$$f" > /dev/null && echo "  OK $$f" || echo "  FAIL $$f"; \
    done

# Run all static checks
check:
    @echo "=== Static Analysis ==="
    just lint-python
    just lint-manifests
    @echo ""
    @echo "=== All checks passed ==="

# ── Testing ──

# Run Python unit tests
test *args="":
    cd cli && uv run pytest {{args}}

# Run tests with coverage
test-cov:
    cd cli && uv run pytest --cov=board --cov-report=term-missing

# Dry run: validate setup inputs without touching Azure
dry-run name="testuser":
    BOARD_NON_INTERACTIVE=1 BOARD_DEV_NAME={{name}} BOARD_ENVIRONMENT=personal {{_board}} up --dry-run --non-interactive

# Test cloud-init locally (requires: brew install multipass, ~5-8 min)
test-cloud-init:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v multipass &>/dev/null; then
        echo "ERROR: multipass not installed. Install: brew install multipass"
        exit 1
    fi
    VM_NAME="board-ci-test"
    multipass delete "$VM_NAME" --purge 2>/dev/null || true
    echo "Launching Ubuntu 24.04 with cloud-init..."
    multipass launch 24.04 --name "$VM_NAME" \
        --cloud-init infra/cloud-init/cloud-init.yaml \
        --cpus 2 --memory 4G --disk 20G
    echo "Waiting for cloud-init (this takes 5-8 minutes)..."
    multipass exec "$VM_NAME" -- cloud-init status --wait
    echo ""
    echo "=== Tool Verification ==="
    PASS=0; FAIL=0
    for cmd in git python3 node docker just jq yq; do
        if multipass exec "$VM_NAME" -- command -v "$cmd" &>/dev/null; then
            echo "  OK  $cmd"
            ((PASS++))
        else
            echo "  FAIL $cmd"
            ((FAIL++))
        fi
    done
    echo ""
    echo "=== Results: $PASS passed, $FAIL failed ==="
    multipass delete "$VM_NAME" --purge
    [ "$FAIL" -eq 0 ]

# ── Help ──

# Show board CLI help
help:
    @{{_board}} --help

# ── Backward Compatibility Aliases ──
alias setup := board
alias admin := shape
alias export-bundle := export-pass
alias provision-projects := install-projects
