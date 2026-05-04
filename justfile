# ── Board Recipes ──

set dotenv-load := true

# Python CLI invocation
_board := "uv run --project cli board"

# Defaults (overridable via env or CLI)
default_rg := env_var_or_default("BOARD_RG", "")
default_sku := "Standard_D2s_v6"
default_location := "australiaeast"

# ── Interactive Setup ──

# Board up — onboard a developer by provisioning a cloud dev environment
board *args="":
    @{{_board}} up {{args}}

# Record a demo of the board wizard (no Azure credentials needed)
demo:
    @{{_board}} up --demo

# Admin — control panel (manage boards, projects, and secrets)
admin:
    @{{_board}} admin

# ── Deployment ──

# Deploy a new board (direct Bicep deploy, no wizard)
create-vm name rg=default_rg sku=default_sku:
    @{{_board}} create-vm {{name}} --rg "{{rg}}" --sku {{sku}}

# Validate Bicep without deploying
validate rg=default_rg:
    @{{_board}} validate --rg "{{rg}}"

# Preview what would change
what-if name rg=default_rg:
    @{{_board}} what-if {{name}} --rg "{{rg}}"

# ── VM Operations ──

# Start a board
start name rg=default_rg:
    @{{_board}} vm start {{name}} --rg "{{rg}}"

# Stop (deallocate) a board
stop name rg=default_rg:
    @{{_board}} vm stop {{name}} --rg "{{rg}}"

# SSH into a board (auto-detects auth method: Entra ID or SSH key)
ssh name *args:
    @{{_board}} vm ssh {{name}} {{args}}

# Show board status
status name rg=default_rg:
    @{{_board}} vm status {{name}} --rg "{{rg}}"

# List all boards and their status
list rg=default_rg:
    @{{_board}} vm ls --rg "{{rg}}"

# ── Access Control ──

# Grant access to a developer (role: admin, developer, or viewer)
grant-access name email rg=default_rg role="developer":
    @{{_board}} vm grant-access {{email}} {{name}} --rg "{{rg}}" --role {{role}}

# ── Teardown ──

# Delete a single board and all associated resources
delete-vm name rg=default_rg confirm="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "{{confirm}}" == "yes" ]]; then
        {{_board}} vm delete {{name}} --rg "{{rg}}" --yes
    else
        {{_board}} vm delete {{name}} --rg "{{rg}}"
    fi

# Delete every board-managed resource inside the resource group (NOT the RG itself)
destroy-all rg=default_rg confirm="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "{{confirm}}" == "yes" ]]; then
        {{_board}} destroy --rg "{{rg}}" --yes
    else
        {{_board}} destroy --rg "{{rg}}"
    fi

# ── SSH Config ──

# Print SSH config block for a developer (auto-detects auth method)
ssh-config name rg=default_rg:
    @{{_board}} ssh-config show {{name}} --rg "{{rg}}"

# Write SSH config block to ~/.ssh/config (idempotent, auto-detects auth method)
ssh-config-write name rg=default_rg:
    @{{_board}} ssh-config write {{name}} --rg "{{rg}}"

# Remove SSH config block for a board
ssh-config-remove name:
    @{{_board}} ssh-config remove {{name}}

# ── Board Passes ──

# Create a board pass (encrypted starter kit) for a developer
export-pass name rg=default_rg:
    @{{_board}} export-pass {{name}} --rg "{{rg}}"

# Create a board pass forcing SSH key auth (regardless of VM tag)
export-ssh-pass name rg=default_rg:
    @{{_board}} export-pass {{name}} --rg "{{rg}}" --auth ssh-key

# ── Utilities ──

# Generate an SSH keypair for a dev
generate-key name:
    @{{_board}} vm keygen {{name}}

# Run smoke tests against a deployed board
smoke-test name:
    @{{_board}} smoke-test {{name}}

# Check cloud-init status on a board
cloud-init-status name rg=default_rg:
    #!/usr/bin/env bash
    set -euo pipefail
    : "${BOARD_RG:=}"
    RG="{{rg}}"
    if [[ -z "$RG" ]]; then
        echo "ERROR: resource group required. Pass as second arg or set BOARD_RG."
        exit 1
    fi
    RG_SUFFIX="${RG#rg-}"
    HOST="devvm-{{name}}.{{default_location}}.cloudapp.azure.com"
    KEY="$HOME/.ssh/devvm-{{name}}"
    # Use Entra cert-based SSH if no key file exists
    if [ -f "$KEY" ]; then
        ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "devuser@$HOST" \
            'cloud-init status --long && test -f ~/.cloud-init-complete && echo "Bootstrap: COMPLETE" || echo "Bootstrap: IN PROGRESS"'
    else
        az ssh vm \
            --resource-group "$RG" \
            --name "vm-${RG_SUFFIX}-{{name}}" \
            -- 'cloud-init status --long && test -f ~/.cloud-init-complete && echo "Bootstrap: COMPLETE" || echo "Bootstrap: IN PROGRESS"'
    fi

# ── Browser Tools ──

# Access Cockpit system admin UI via SSH tunnel (localhost:9091 → VM:9190)
cockpit name:
    #!/usr/bin/env bash
    set -euo pipefail
    HOST="devvm-{{name}}.{{default_location}}.cloudapp.azure.com"
    KEY="$HOME/.ssh/devvm-{{name}}"
    echo "Opening SSH tunnel to Cockpit..."
    echo "Open http://localhost:9091 in your browser."
    echo ""
    echo "Press Ctrl+C to close the tunnel."
    if [ -f "$KEY" ]; then
        ssh -L 9091:localhost:9190 -N -i "$KEY" "devuser@$HOST"
    else
        CERT_DIR="$HOME/.ssh/board-entra/devvm-{{name}}"
        if [ -f "$CERT_DIR/id_rsa" ]; then
            ssh -L 9091:localhost:9190 -N \
                -i "$CERT_DIR/id_rsa" \
                -o "CertificateFile=$CERT_DIR/id_rsa.pub-aadcert.pub" \
                "$HOST"
        else
            echo "ERROR: No SSH key or Entra certificate found for devvm-{{name}}."
            echo "Run: just ssh-config-write {{name}}"
            exit 1
        fi
    fi

# Access Portainer Docker management UI via SSH tunnel (localhost:9444 → VM:9443)
portainer name:
    #!/usr/bin/env bash
    set -euo pipefail
    HOST="devvm-{{name}}.{{default_location}}.cloudapp.azure.com"
    KEY="$HOME/.ssh/devvm-{{name}}"
    echo "Opening SSH tunnel to Portainer..."
    echo "Open https://localhost:9444 in your browser."
    echo "Accept the self-signed certificate warning."
    echo ""
    echo "Press Ctrl+C to close the tunnel."
    if [ -f "$KEY" ]; then
        ssh -L 9444:localhost:9443 -N -i "$KEY" "devuser@$HOST"
    else
        CERT_DIR="$HOME/.ssh/board-entra/devvm-{{name}}"
        if [ -f "$CERT_DIR/id_rsa" ]; then
            ssh -L 9444:localhost:9443 -N \
                -i "$CERT_DIR/id_rsa" \
                -o "CertificateFile=$CERT_DIR/id_rsa.pub-aadcert.pub" \
                "$HOST"
        else
            echo "ERROR: No SSH key or Entra certificate found for devvm-{{name}}."
            echo "Run: just ssh-config-write {{name}}"
            exit 1
        fi
    fi

# Access code-server via SSH tunnel (opens browser IDE at localhost:8080)
code-server name:
    #!/usr/bin/env bash
    set -euo pipefail
    HOST="devvm-{{name}}.{{default_location}}.cloudapp.azure.com"
    KEY="$HOME/.ssh/devvm-{{name}}"
    echo "Opening SSH tunnel to code-server..."
    echo "Open http://localhost:8080 in your browser."
    if [ -f "$KEY" ]; then
        SSH_CMD="ssh -i $KEY devuser@$HOST"
    else
        CERT_DIR="$HOME/.ssh/board-entra/devvm-{{name}}"
        if [ -f "$CERT_DIR/id_rsa" ]; then
            SSH_CMD="ssh -i $CERT_DIR/id_rsa -o CertificateFile=$CERT_DIR/id_rsa.pub-aadcert.pub $HOST"
        else
            echo "ERROR: No SSH key or Entra certificate found for devvm-{{name}}."
            echo "Run: just ssh-config-write {{name}}"
            exit 1
        fi
    fi
    PASS=$($SSH_CMD 'cat ~/.board/code-server-password 2>/dev/null || echo "unknown"')
    echo "Password: $PASS"
    echo ""
    echo "Press Ctrl+C to close the tunnel."
    $SSH_CMD -L 8080:localhost:8080 -N

# Forward all listening ports from a VM to localhost (dynamic discovery)
tunnel-all name:
    #!/usr/bin/env bash
    set -euo pipefail
    source cli/scripts/board-ssh.sh
    board_forward_ports {{name}}

# ── VS Code Tunnel ──

# Set up VS Code Tunnel on a board (interactive GitHub auth)
tunnel-setup name:
    #!/usr/bin/env bash
    set -euo pipefail
    HOST="devvm-{{name}}.{{default_location}}.cloudapp.azure.com"
    KEY="$HOME/.ssh/devvm-{{name}}"
    # Build SSH base command depending on auth method
    if [ -f "$KEY" ]; then
        SSH_CMD="ssh -i $KEY devuser@$HOST"
        SSH_CMD_T="ssh -t -i $KEY devuser@$HOST"
    else
        CERT_DIR="$HOME/.ssh/board-entra/devvm-{{name}}"
        if [ -f "$CERT_DIR/id_rsa" ]; then
            SSH_CMD="ssh -i $CERT_DIR/id_rsa -o CertificateFile=$CERT_DIR/id_rsa.pub-aadcert.pub $HOST"
            SSH_CMD_T="ssh -t -i $CERT_DIR/id_rsa -o CertificateFile=$CERT_DIR/id_rsa.pub-aadcert.pub $HOST"
        else
            echo "ERROR: No SSH key or Entra certificate found for devvm-{{name}}."
            echo "Run: just ssh-config-write {{name}}"
            exit 1
        fi
    fi
    echo "Setting up VS Code Tunnel on devvm-{{name}}..."
    if ! $SSH_CMD "test -x /usr/local/bin/code" 2>/dev/null; then
        echo "ERROR: VS Code CLI not installed on devvm-{{name}}."
        exit 1
    fi
    $SSH_CMD_T '/usr/local/bin/code tunnel user login --provider github'
    $SSH_CMD 'sudo hostnamectl set-hostname "devvm-{{name}}"' || true
    $SSH_CMD '/usr/local/bin/code tunnel service uninstall 2>/dev/null; true'
    $SSH_CMD '/usr/local/bin/code tunnel service install --accept-server-license-terms && echo "https://vscode.dev/tunnel/devvm-{{name}}" > ~/.board/tunnel-url'
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

# ── Governance ──

# Show policy enforcement rules
policies:
    @{{_board}} policies

# Show cost breakdown for all boards
costs rg=default_rg:
    @{{_board}} costs --rg "{{rg}}"

# Show cost breakdown for a specific developer
costs-dev name rg=default_rg:
    @{{_board}} costs --rg "{{rg}}" --developer {{name}}

# ── Project Dev Workflow ──

# Start a project's dev workflow on the VM and forward its ports to localhost
dev name project:
    @bash cli/scripts/board-dev.sh start {{name}} {{project}}

# Stop a running project (kills its tmux session on the VM)
dev-stop name project:
    @bash cli/scripts/board-dev.sh stop {{name}} {{project}}

# Attach to the project's tmux session over SSH (Ctrl+B d to detach)
dev-logs name project:
    @bash cli/scripts/board-dev.sh logs {{name}} {{project}}

# List running project sessions on the VM
dev-list name:
    @bash cli/scripts/board-dev.sh list {{name}}

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

# Show status of all boards in a resource group
fleet-status rg=default_rg:
    @{{_board}} fleet --rg "{{rg}}"

# Auto-detect project stack and generate a manifest
init:
    @{{_board}} init

# ── Automation ──

# Wait for cloud-init to complete on a board (polls with progress)
wait-ready name:
    @{{_board}} wait-ready {{name}}

# Preflight checks before deploying a board
preflight name rg=default_rg sku=default_sku:
    @{{_board}} preflight {{name}} --rg "{{rg}}" --sku {{sku}}

# Provision a board from zero to ready (one command does everything)
provision name rg=default_rg sku=default_sku:
    BOARD_NON_INTERACTIVE=1 BOARD_DEV_NAME={{name}} BOARD_RG={{rg}} BOARD_VM_SKU={{sku}} {{_board}} up --non-interactive

# Rotate SSH key for a board (invalidates existing board passes)
rotate-key name:
    @{{_board}} rotate-key {{name}}

# Build the VS Code extension (.vsix)
build-extension:
    cd extension && npm run build:prod && npx @vscode/vsce package --no-dependencies

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
dry-run name="testuser" rg=default_rg:
    BOARD_NON_INTERACTIVE=1 BOARD_DEV_NAME={{name}} BOARD_RG={{rg}} {{_board}} up --dry-run --non-interactive

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
alias shape := admin
alias export-bundle := export-pass
alias provision-projects := install-projects
