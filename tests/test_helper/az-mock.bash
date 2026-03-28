# tests/test_helper/az-mock.bash
# Mock az CLI — returns canned responses based on arguments
az() {
    local args="$*"
    echo "az $args" >> "${BATS_TMPDIR}/az-calls.log"

    case "$args" in
        *"account show"*)
            cat "${BATS_TEST_DIRNAME}/test_helper/fixtures/account-show.json"
            ;;
        *"ad signed-in-user show"*)
            echo "00000000-0000-0000-0000-000000000001"
            ;;
        *"keyvault show --name"*"--query 'id'"*|*"keyvault show --name"*"--query id"*)
            if [[ "${AZ_MOCK_KV_STATE:-absent}" == "exists" || "${AZ_MOCK_KV_STATE:-absent}" == "recovered" ]]; then
                echo "/subscriptions/00000000/resourceGroups/rg-test/providers/Microsoft.KeyVault/vaults/kv-test"
            else
                return 1
            fi
            ;;
        *"keyvault show --name"*"--query"*"name"*|*"keyvault show --name"*"-o tsv"*)
            if [[ "${AZ_MOCK_KV_STATE:-absent}" == "exists" || "${AZ_MOCK_KV_STATE:-absent}" == "recovered" ]]; then
                echo "kv-test"
            else
                return 1
            fi
            ;;
        *"keyvault show-deleted --name"*)
            if [[ "${AZ_MOCK_KV_STATE:-absent}" == "soft-deleted" ]]; then
                echo "kv-test"
            else
                echo "" ; return 1
            fi
            ;;
        *"keyvault recover"*)
            if [[ "${AZ_MOCK_KV_RECOVER_FAILS:-false}" == "true" ]]; then
                echo "Recovery failed" >&2; return 1
            fi
            AZ_MOCK_KV_STATE=recovered
            return 0
            ;;
        *"keyvault purge"*)
            AZ_MOCK_KV_STATE=absent
            return 0
            ;;
        *"keyvault create"*)
            if [[ "${AZ_MOCK_KV_STATE:-absent}" == "soft-deleted" ]]; then
                echo "ConflictError: A vault with the same name already exists in deleted state" >&2
                return 1
            fi
            if [[ "${AZ_MOCK_KV_CREATE_CONFLICT:-false}" == "true" ]]; then
                AZ_MOCK_KV_CREATE_CONFLICT=false  # only fail once
                AZ_MOCK_KV_STATE=soft-deleted      # transition to soft-deleted so retry can find it
                echo "ConflictError: A vault with the same name already exists in deleted state" >&2
                return 1
            fi
            AZ_MOCK_KV_STATE=exists
            return 0
            ;;
        *"role assignment list"*)
            echo ""
            return 0
            ;;
        *"role assignment create"*)
            return 0
            ;;
        *"group delete"*)
            return 0
            ;;
        *"group show"*)
            return 0
            ;;
        *"group create"*)
            return 0
            ;;
        *"deployment group create"*)
            echo '{"properties":{"outputs":{"vmName":{"value":"vm-test"},"publicIpAddress":{"value":"1.2.3.4"},"fqdn":{"value":"test.australiaeast.cloudapp.azure.com"},"sshCommand":{"value":"ssh devuser@test"}}}}'
            ;;
        *)
            echo "UNMOCKED: az $args" >&2
            return 1
            ;;
    esac
}
export -f az
