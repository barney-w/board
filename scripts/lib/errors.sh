#!/usr/bin/env bash
# Human-readable error messages for common Azure CLI and deployment failures

# Parse and display a helpful error message from Azure CLI output
# Usage: handle_deploy_error "$error_output" "$name"
handle_deploy_error() {
    local output="$1"
    local name="${2:-}"

    case "$output" in
        *SkuNotAvailable*)
            echo ""
            echo "ERROR: VM size is not available in this region."
            echo "  The requested SKU has capacity restrictions."
            echo ""
            echo "  Fix: Specify a different SKU:"
            echo "    just create-vm ${name} sku=Standard_D2s_v6"
            echo ""
            echo "  To check available SKUs:"
            echo "    az vm list-skus --location australiaeast --output table | grep Standard_D"
            ;;
        *BCP427*SSH_PUB_KEY*|*SSH_PUB_KEY*does\ not\ exist*)
            echo ""
            echo "ERROR: SSH public key not configured."
            echo ""
            echo "  Fix: Generate a key first, then deploy:"
            echo "    just generate-key ${name}"
            echo "    just create-vm ${name}"
            echo ""
            echo "  Or set the env var manually:"
            echo "    export SSH_PUB_KEY=\"\$(cat ~/.ssh/devvm-${name}.pub)\""
            ;;
        *AuthorizationFailed*)
            echo ""
            echo "ERROR: You don't have permission to deploy to this subscription."
            echo ""
            echo "  Fix: Check you're logged into the right subscription:"
            echo "    az account show"
            echo "    az login"
            ;;
        *ResourceGroupNotFound*)
            echo ""
            echo "ERROR: Resource group not found."
            echo ""
            echo "  Fix: Create it first:"
            echo "    just create-rg"
            ;;
        *InvalidTemplateDeployment*|*DeploymentFailed*)
            echo ""
            echo "ERROR: Bicep deployment failed."
            echo "  Check the Azure portal for detailed error messages, or run:"
            echo "    just validate"
            ;;
        *Host\ key\ verification\ failed*)
            echo ""
            echo "ERROR: SSH host key mismatch (VM was probably redeployed)."
            echo ""
            echo "  Fix: Clear the old host key:"
            echo "    ssh-keygen -R devvm-${name}.australiaeast.cloudapp.azure.com"
            ;;
        *)
            # No specific handler — show the raw error
            echo "$output"
            ;;
    esac
}
