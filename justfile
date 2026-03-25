# ── Board Recipes ──

set dotenv-load := true

# Defaults (overridable via env or CLI)
default_env := "personal"
default_sku := "Standard_D2s_v6"
default_location := "australiaeast"
default_region := "aue"

# ── Interactive Setup ──

# Board up — onboard a developer by provisioning a cloud dev environment
board *args="":
    @bash scripts/setup.sh {{args}}

# Shape — shaper's control panel (manage boards, projects, and secrets)
shape:
    @bash scripts/admin.sh

# ── Deployment ──

# Deploy a new board
create-vm name env=default_env sku=default_sku:
    #!/usr/bin/env bash
    set -euo pipefail
    # Auto-resolve SSH_PUB_KEY if not set
    if [[ -z "${SSH_PUB_KEY:-}" ]]; then
        key_file="$HOME/.ssh/devvm-{{name}}.pub"
        if [[ -f "$key_file" ]]; then
            export SSH_PUB_KEY="$(cat "$key_file")"
            echo "Using SSH key from $key_file"
        else
            echo "ERROR: SSH_PUB_KEY not set and ~/.ssh/devvm-{{name}}.pub not found."
            echo "Fix: Run 'just generate-key {{name}}' first, or set SSH_PUB_KEY."
            exit 1
        fi
    fi
    # Clear known_hosts entry (handles redeploy case)
    ssh-keygen -R "devvm-{{name}}.{{default_location}}.cloudapp.azure.com" 2>/dev/null || true
    echo "Shaping board for {{name}} in {{env}} environment..."
    az deployment group create \
        --resource-group "rg-{{env}}-{{default_region}}-devvm" \
        --template-file infra/main.bicep \
        --parameters "infra/config/{{env}}.bicepparam" \
        --parameters developerName='{{name}}' vmSku='{{sku}}' \
        --name "deploy-{{name}}-$(date -u +%Y%m%d%H%M%S)" \
        --verbose
    echo "Board shaped. Run 'just ssh {{name}}' to connect."

# Create the resource group (run once per environment)
create-rg env=default_env:
    az group create \
        --name rg-{{env}}-{{default_region}}-devvm \
        --location {{default_location}} \
        --tags project=devvm environment={{env}} managed-by=bicep

# Validate Bicep without deploying
validate env=default_env:
    az deployment group validate \
        --resource-group rg-{{env}}-{{default_region}}-devvm \
        --template-file infra/main.bicep \
        --parameters infra/config/{{env}}.bicepparam

# Preview what would change
what-if name env=default_env:
    az deployment group what-if \
        --resource-group rg-{{env}}-{{default_region}}-devvm \
        --template-file infra/main.bicep \
        --parameters infra/config/{{env}}.bicepparam \
        --parameters developerName='{{name}}'

# ── VM Operations ──

# Start a board
start name env=default_env:
    az vm start \
        --resource-group rg-{{env}}-{{default_region}}-devvm \
        --name vm-{{env}}-{{default_region}}-devvm-{{name}} \
        --no-wait
    @echo "Board starting. Give it ~30s then run 'just ssh {{name}}'."

# Stop (deallocate) a board
stop name env=default_env:
    az vm deallocate \
        --resource-group rg-{{env}}-{{default_region}}-devvm \
        --name vm-{{env}}-{{default_region}}-devvm-{{name}} \
        --no-wait
    @echo "Board deallocating. Compute charges will stop."

# SSH into a board
ssh name env=default_env:
    ssh -i ~/.ssh/devvm-{{name}} devuser@devvm-{{name}}.{{default_location}}.cloudapp.azure.com

# Show board status
status name env=default_env:
    az vm get-instance-view \
        --resource-group rg-{{env}}-{{default_region}}-devvm \
        --name vm-{{env}}-{{default_region}}-devvm-{{name}} \
        --query '{name:name, status:instanceView.statuses[1].displayStatus, ip:publicIps}' \
        --output table

# List all boards and their status
list env=default_env:
    az vm list \
        --resource-group rg-{{env}}-{{default_region}}-devvm \
        --show-details \
        --query '[].{name:name, status:powerState, ip:publicIps, size:hardwareProfile.vmSize}' \
        --output table

# ── Teardown ──

# Delete a single board and all associated resources (pass confirm=yes to skip prompt)
delete-vm name env=default_env confirm="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "{{confirm}}" != "yes" ]]; then
        echo "WARNING: This will delete vm-{{env}}-{{default_region}}-devvm-{{name}} and all associated resources."
        echo "Press Ctrl+C to cancel, or Enter to continue."
        read _
    fi
    az vm delete \
        --resource-group "rg-{{env}}-{{default_region}}-devvm" \
        --name "vm-{{env}}-{{default_region}}-devvm-{{name}}" \
        --force-deletion true \
        --yes
    # Delete orphaned PIP (not auto-deleted with VM)
    az network public-ip delete \
        --resource-group "rg-{{env}}-{{default_region}}-devvm" \
        --name "pip-{{env}}-{{default_region}}-devvm-{{name}}" \
        2>/dev/null || true
    # Delete auto-shutdown schedule
    az resource delete \
        --resource-group "rg-{{env}}-{{default_region}}-devvm" \
        --resource-type "Microsoft.DevTestLab/schedules" \
        --name "shutdown-computevm-vm-{{env}}-{{default_region}}-devvm-{{name}}" \
        2>/dev/null || true
    # Clear known_hosts entry
    ssh-keygen -R "devvm-{{name}}.{{default_location}}.cloudapp.azure.com" 2>/dev/null || true
    echo "Board deleted (VM, NIC, OS disk, public IP, shutdown schedule)."

# Delete entire environment (nuclear option, pass confirm=yes to skip prompt)
destroy-all env=default_env confirm="":
    #!/usr/bin/env bash
    set -euo pipefail
    RG="rg-{{env}}-{{default_region}}-devvm"
    if [[ "{{confirm}}" != "yes" ]]; then
        echo "WARNING: This will delete the ENTIRE resource group ${RG}."
        echo "Press Ctrl+C to cancel, or Enter to continue."
        read _
    fi
    # Check if RG exists at all
    if ! az group show --name "$RG" &>/dev/null 2>&1; then
        echo "Resource group ${RG} does not exist. Nothing to delete."
        # Still purge any orphaned soft-deleted Key Vaults
        for kv in $(az keyvault list-deleted --query "[?properties.vaultId && contains(properties.vaultId, '${RG}')].name" -o tsv 2>/dev/null || true); do
            echo "Purging orphaned soft-deleted Key Vault: $kv"
            az keyvault purge --name "$kv" 2>/dev/null || true
        done
        exit 0
    fi
    # Discover Key Vaults in the resource group before deleting (for soft-delete purge)
    KV_NAMES=$(az keyvault list --resource-group "$RG" --query '[].name' -o tsv 2>/dev/null || true)
    echo "Deleting resource group ${RG} (this may take a few minutes)..."
    rc=0
    az group delete --name "$RG" --yes || rc=$?
    if (( rc == 130 )) || (( rc == 2 )); then
        echo ""
        echo "Wait cancelled — deletion is still running server-side on Azure."
        echo "Check status:  az group show --name $RG --query properties.provisioningState -o tsv"
        echo "Retry purge:   just destroy-all {{env}} confirm=yes"
        exit 0
    elif (( rc != 0 )); then
        echo "ERROR: Resource group deletion failed (exit $rc). Check Azure portal."
        exit 1
    fi
    echo "Resource group ${RG} deleted."
    # Purge soft-deleted Key Vaults so names can be reused immediately
    if [[ -n "$KV_NAMES" ]]; then
        for kv in $KV_NAMES; do
            echo "Purging soft-deleted Key Vault: $kv"
            az keyvault purge --name "$kv" 2>/dev/null || true
        done
        echo "Key Vault purge complete."
    fi

# ── Utilities ──

# Generate an SSH keypair for a dev
generate-key name:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -f "$HOME/.ssh/devvm-{{name}}" ]]; then
        echo "SSH key already exists: ~/.ssh/devvm-{{name}}"
        echo "Public key: $(cat "$HOME/.ssh/devvm-{{name}}.pub")"
        exit 0
    fi
    ssh-keygen -t ed25519 -C "devvm-{{name}}" -f "$HOME/.ssh/devvm-{{name}}" -N ""
    echo "Public key:"
    cat "$HOME/.ssh/devvm-{{name}}.pub"

# ── Static Analysis ──

# Lint shell scripts with shellcheck
lint-shell:
    shellcheck -x -P scripts -P scripts/lib scripts/*.sh scripts/lib/*.sh

# Validate project manifest YAML syntax
lint-manifests:
    @for f in projects/*.project.yaml projects/examples/*.project.yaml; do \
        [ -f "$$f" ] || continue; \
        yq eval '.' "$$f" > /dev/null && echo "  OK $$f" || echo "  FAIL $$f"; \
    done

# Run all static checks
check:
    @echo "=== Static Analysis ==="
    just lint-shell
    just lint-manifests
    @echo ""
    @echo "=== All checks passed ==="

# ── Testing ──

# Run all bats unit tests
test:
    bats tests/

# Run a specific test file
test-one file:
    bats tests/{{file}}.bats
