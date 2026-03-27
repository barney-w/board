#!/usr/bin/env bash
# Fleet status — collect and display metrics from all running boards
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ui.sh
source "${SCRIPT_DIR}/lib/ui.sh"

ENV="${1:-personal}"
# shellcheck disable=SC2034 # used by caller via just recipe
LOCATION="${2:-australiaeast}"
REGION="${3:-aue}"
RG="rg-${ENV}-${REGION}-devvm"

ui_header "Fleet Status"

# ── List all VMs ──
vm_list=$(az vm list --resource-group "$RG" --show-details \
    --query '[].{name:name, status:powerState, ip:publicIps, size:hardwareProfile.vmSize}' \
    -o tsv 2>/dev/null) || true

if [[ -z "$vm_list" ]]; then
    ui_info "No boards found in $RG"
    exit 0
fi

total=0
active=0
ttfc_sum=0
ttfc_count=0
health_total=0
health_passed=0
declare -a board_lines=()
declare -a issues_list=()

green=$'\033[32m'
grey=$'\033[90m'
yellow=$'\033[33m'
red=$'\033[31m'
bold=$'\033[1m'
# shellcheck disable=SC2034 # used in output formatting below
dim=$'\033[2m'
reset=$'\033[0m'

while IFS=$'\t' read -r name status ip size; do
    ((total++)) || true
    dev_name="${name##*devvm-}"

    dot="${grey}○${reset}"
    display_status="stopped"
    case "$status" in
        *running*) dot="${green}●${reset}"; display_status="running"; ((active++)) || true ;;
        *starting*|*deallocating*) dot="${yellow}◉${reset}"; display_status="transitioning" ;;
        *) dot="${grey}○${reset}"; display_status="stopped" ;;
    esac

    # Collect metrics from running VMs
    ttfc_str=""
    health_str=""
    if [[ "$status" == *running* ]] && [[ -n "$ip" ]]; then
        ssh_key="$HOME/.ssh/devvm-${dev_name}"
        if [[ -f "$ssh_key" ]]; then
            # Read metrics (best effort, 5s timeout)
            metrics=$( ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no \
                -i "$ssh_key" "devuser@${ip}" \
                'cat ~/.board/metrics.json 2>/dev/null; echo "---"; cat ~/.board/last-check 2>/dev/null' \
                2>/dev/null ) || metrics=""

            if [[ -n "$metrics" ]]; then
                json_part="${metrics%%---*}"
                check_part="${metrics#*---}"

                # Extract TTFC
                ttfc=$(echo "$json_part" | grep -o '"time_to_first_commit_minutes": [0-9]*' | grep -o '[0-9]*' || true)
                if [[ -n "$ttfc" ]]; then
                    ttfc_str="${ttfc}m"
                    ((ttfc_sum += ttfc)) || true
                    ((ttfc_count++)) || true
                fi

                # Extract health
                h_passed=$(echo "$check_part" | grep -o 'PASSED=[0-9]*' | grep -o '[0-9]*' || true)
                h_total=$(echo "$check_part" | grep -o 'TOTAL=[0-9]*' | grep -o '[0-9]*' || true)
                # shellcheck disable=SC2034 # reserved for future per-board failure display
                h_failed=$(echo "$check_part" | grep -o 'FAILED=[0-9]*' | grep -o '[0-9]*' || true)
                if [[ -n "$h_total" ]] && [[ "$h_total" -gt 0 ]]; then
                    health_str="${h_passed}/${h_total}"
                    ((health_total += h_total)) || true
                    ((health_passed += h_passed)) || true
                fi

                # Collect issues
                h_issues=$(echo "$check_part" | grep -o 'ISSUES=.*' | sed 's/ISSUES=//' || true)
                if [[ -n "$h_issues" ]] && [[ "$h_issues" != "none" ]]; then
                    issues_list+=("${dev_name}: ${h_issues}")
                fi
            fi
        fi
    fi

    board_lines+=("$(printf "  %s  %-14s %-14s %-12s %-8s %-8s %s" \
        "$dot" "$dev_name" "$display_status" "$size" "${ttfc_str:----}" "${health_str:----}" "${ip:-—}")")
done <<< "$vm_list"

# ── Display ──
echo ""
echo "  ${bold}Boards${reset}  ${active} active / ${total} total"
echo ""
printf "  %-3s %-14s %-14s %-12s %-8s %-8s %s\n" "" "NAME" "STATUS" "SIZE" "TTFC" "HEALTH" "IP"
echo "  $(printf '%.0s─' {1..80})"
for line in "${board_lines[@]}"; do
    echo "$line"
done
echo ""

# ── Aggregates ──
if ((ttfc_count > 0)); then
    avg_ttfc=$((ttfc_sum / ttfc_count))
    echo "  ${bold}Avg TTFC${reset}     ${avg_ttfc} minutes (across ${ttfc_count} boards)"
fi

if ((health_total > 0)); then
    health_pct=$((health_passed * 100 / health_total))
    echo "  ${bold}Health${reset}       ${health_passed}/${health_total} checks passing (${health_pct}%)"
fi

if ((${#issues_list[@]} > 0)); then
    echo ""
    echo "  ${bold}Common Issues${reset}"
    for issue in "${issues_list[@]}"; do
        echo "    ${red}!${reset} ${issue}"
    done
fi

echo ""
