#!/usr/bin/env bash
# Manifest parser — requires yq

if ! command -v yq &>/dev/null; then
    echo "Error: yq is required for manifest parsing. Install: https://github.com/mikefarah/yq" >&2
    return 1
fi

# ── Query helpers ──

manifest_list_projects() {
    local dir="$1"
    for f in "${dir}"/*.project.yaml; do
        [[ -f "$f" ]] || continue
        yq eval '.name + "|" + .description' "$f"
    done
}

manifest_get() {
    local result
    result=$(yq eval "$2" "$1" 2>/dev/null)
    [[ "$result" == "null" ]] && result=""
    echo "$result"
}

manifest_get_keyvault_secrets() {
    local all_secrets=""
    for manifest in "$@"; do
        while IFS= read -r secret_name; do
            [[ -z "$secret_name" || "$secret_name" == "null" ]] && continue
            all_secrets="${all_secrets}${secret_name}"$'\n'
        done < <(yq eval '.env.keyvault_secrets.[]' "$manifest" 2>/dev/null)
    done
    # Deduplicate while preserving order
    echo -n "$all_secrets" | awk '!seen[$0]++'
}

manifest_get_required_env() {
    local manifest="$1"
    yq eval '.env.required[]' "$manifest" 2>/dev/null
}

# ── Systemd unit generation ──

manifest_generate_systemd_unit() {
    local manifest="$1"
    local idx="$2"
    local project_path="$3"

    local description exec_cmd working_dir env_file extra_path
    description=$(manifest_get "$manifest" ".services[$idx].description")
    exec_cmd=$(manifest_get "$manifest" ".services[$idx].exec")
    working_dir=$(manifest_get "$manifest" ".services[$idx].working_dir")
    env_file=$(manifest_get "$manifest" ".services[$idx].env_file")
    extra_path=$(manifest_get "$manifest" ".services[$idx].extra_path")

    cat <<EOF
[Unit]
Description=${description}
After=default.target

[Service]
Type=simple
ExecStart=${project_path}/${exec_cmd}
WorkingDirectory=${project_path}/${working_dir}
EnvironmentFile=${project_path}/${env_file}
Environment=PATH=${project_path}/${extra_path}:/usr/local/bin:/usr/bin:/bin
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
}

# ── VS Code file generation ──

manifest_generate_vscode_tasks() {
    local manifest="$1"
    local count
    count=$(yq eval '.vscode.tasks | length' "$manifest")

    local tasks_json="[]"
    for (( i = 0; i < count; i++ )); do
        local t_label t_command t_background t_group
        t_label=$(manifest_get "$manifest" ".vscode.tasks[$i].label")
        t_command=$(manifest_get "$manifest" ".vscode.tasks[$i].command")
        t_background=$(manifest_get "$manifest" ".vscode.tasks[$i].background")
        t_group=$(manifest_get "$manifest" ".vscode.tasks[$i].group")

        local task
        task=$(jq -n --arg lbl "$t_label" --arg cmd "$t_command" \
            '{"label": $lbl, "type": "shell", "command": $cmd, "problemMatcher": []}')

        if [[ "$t_background" == "true" ]]; then
            task=$(echo "$task" | jq '. + {"isBackground": true}')
        fi

        if [[ -n "$t_group" ]]; then
            task=$(echo "$task" | jq --arg grp "$t_group" '. + {"group": $grp}')
        fi

        tasks_json=$(echo "$tasks_json" | jq --argjson t "$task" '. + [$t]')
    done

    jq -n --argjson t "$tasks_json" '{"version": "2.0.0", "tasks": $t}'
}

manifest_generate_vscode_launch() {
    local manifest="$1"
    local count
    count=$(yq eval '.vscode.launch | length' "$manifest")

    local configs_json="[]"
    for (( i = 0; i < count; i++ )); do
        local l_name l_type l_request l_module l_cwd l_env_file l_plt
        l_name=$(manifest_get "$manifest" ".vscode.launch[$i].name")
        l_type=$(manifest_get "$manifest" ".vscode.launch[$i].type")
        l_request=$(manifest_get "$manifest" ".vscode.launch[$i].request")
        l_module=$(manifest_get "$manifest" ".vscode.launch[$i].module")
        l_cwd=$(manifest_get "$manifest" ".vscode.launch[$i].cwd")
        l_env_file=$(manifest_get "$manifest" ".vscode.launch[$i].env_file")
        l_plt=$(manifest_get "$manifest" ".vscode.launch[$i].pre_launch_task")

        # Build args array
        local args_json
        args_json=$(yq eval -o=json ".vscode.launch[$i].args" "$manifest" 2>/dev/null)
        [[ "$args_json" == "null" ]] && args_json="[]"

        local config
        config=$(jq -n \
            --arg n "$l_name" \
            --arg tp "$l_type" \
            --arg rq "$l_request" \
            --arg md "$l_module" \
            --argjson args "$args_json" \
            '{"name": $n, "type": $tp, "request": $rq, "module": $md, "args": $args}')

        if [[ -n "$l_cwd" ]]; then
            config=$(echo "$config" | jq --arg v "\${workspaceFolder}/$l_cwd" '. + {"cwd": $v}')
        fi

        if [[ -n "$l_env_file" ]]; then
            config=$(echo "$config" | jq --arg v "\${workspaceFolder}/$l_env_file" '. + {"envFile": $v}')
        fi

        if [[ -n "$l_plt" ]]; then
            config=$(echo "$config" | jq --arg v "$l_plt" '. + {"preLaunchTask": $v}')
        fi

        configs_json=$(echo "$configs_json" | jq --argjson c "$config" '. + [$c]')
    done

    jq -n --argjson c "$configs_json" '{"version": "0.2.0", "configurations": $c}'
}

manifest_generate_vscode_settings() {
    local manifest="$1"
    yq eval -o=json '.vscode.settings' "$manifest" 2>/dev/null
}

# ── Workspace generation ──

manifest_generate_workspace() {
    local folders_json="[]"
    local ports_json="{}"

    for manifest in "$@"; do
        local name description rel_path
        name=$(manifest_get "$manifest" ".name")
        description=$(manifest_get "$manifest" ".description")

        # Derive relative path from manifest dir
        rel_path=$(manifest_get "$manifest" ".path")
        # Convert ~/projects/<name> to just the project name for workspace relative paths
        rel_path="${rel_path##*/}"

        local folder
        folder=$(jq -n --arg p "$rel_path" --arg n "$name ($description)" \
            '{"path": $p, "name": $n}')
        folders_json=$(echo "$folders_json" | jq --argjson f "$folder" '. + [$f]')

        # Collect port attributes
        local port_keys
        port_keys=$(yq eval '.vscode.ports | keys | .[]' "$manifest" 2>/dev/null)
        while IFS= read -r port; do
            [[ -z "$port" || "$port" == "null" ]] && continue
            local label auto_forward
            label=$(manifest_get "$manifest" ".vscode.ports.\"$port\".label")
            auto_forward=$(manifest_get "$manifest" ".vscode.ports.\"$port\".auto_forward")

            # Map auto_forward values: notify -> onAutoForward: notify, silent -> onAutoForward: silent
            local port_attr
            port_attr=$(jq -n --arg lbl "$label" --arg af "$auto_forward" \
                '{"label": $lbl, "onAutoForward": $af}')
            ports_json=$(echo "$ports_json" | jq --arg k "$port" --argjson v "$port_attr" '. + {($k): $v}')
        done <<< "$port_keys"
    done

    jq -n \
        --argjson f "$folders_json" \
        --argjson p "$ports_json" \
        '{"folders": $f, "settings": {"remote.portsAttributes": $p, "remote.autoForwardPortsSource": "process", "task.allowAutomaticTasks": "on"}}'
}

# ── Health check script generation ──

manifest_generate_check_script() {
    cat <<'HEADER'
#!/usr/bin/env bash
set -euo pipefail

# Board Health Check — auto-generated from project manifests

pass=0
fail=0
issues=()

green=$'\033[32m'
red=$'\033[31m'
yellow=$'\033[33m'
bold=$'\033[1m'
dim=$'\033[2m'
sky=$'\033[38;2;14;165;233m'
reset=$'\033[0m'

_checks_in_section=0
_section_total=0

check() {
    local label="$1" detail="$2"
    shift 2
    ((_checks_in_section++)) || true
    local prefix
    if (( _checks_in_section == _section_total )); then
        prefix="└─"
    else
        prefix="├─"
    fi
    # Dot-leader: pad label to 22 chars with dots
    local padded
    padded=$(printf '%-22s' "$label")
    padded="${padded// /.}"
    if eval "$@" &>/dev/null; then
        echo "  ${prefix} ${padded} ${detail} ${green}✓${reset}"
        ((pass++)) || true
    else
        echo "  ${prefix} ${padded} ${detail} ${red}✗${reset}"
        ((fail++)) || true
        issues+=("${label}")
    fi
}

check_with_hint() {
    local label="$1" detail="$2" hint="$3"
    shift 3
    ((_checks_in_section++)) || true
    local prefix
    if (( _checks_in_section == _section_total )); then
        prefix="└─"
    else
        prefix="├─"
    fi
    local padded
    padded=$(printf '%-22s' "$label")
    padded="${padded// /.}"
    if eval "$@" &>/dev/null; then
        echo "  ${prefix} ${padded} ${detail} ${green}✓${reset}"
        ((pass++)) || true
    else
        echo "  ${prefix} ${padded} ${detail} ${red}✗${reset}"
        ((fail++)) || true
        issues+=("${label}")
        echo "     ${dim}→ ${hint}${reset}"
    fi
}

echo ""
echo "  ${sky}${bold}Board Check${reset}"
echo "  ${dim}═══════════${reset}"

# ── System health ──
echo ""
echo "  ${bold}System${reset}"
_checks_in_section=0
_section_total=5

# Docker
docker_status="not running"
if systemctl is-active --quiet docker 2>/dev/null; then
    docker_status="running"
fi
check "Docker" "$docker_status" "systemctl is-active --quiet docker"

# Disk
disk_pct=$(df / --output=pcent 2>/dev/null | tail -1 | tr -d ' %' || echo 0)
disk_free=$(df -h / --output=avail 2>/dev/null | tail -1 | tr -d ' ' || echo "?")
check "Disk" "${disk_pct}% (${disk_free} free)" "test $disk_pct -lt 90"

# Memory
mem_used=$(free -m 2>/dev/null | awk '/Mem:/{printf "%.1f", ($3)/1024}' || echo "?")
mem_total=$(free -m 2>/dev/null | awk '/Mem:/{printf "%.1f", ($2)/1024}' || echo "?")
mem_avail=$(free -m 2>/dev/null | awk '/Mem:/{print $7}' || echo 1024)
check "Memory" "${mem_used} / ${mem_total} GB" "test $mem_avail -gt 256"

# code-server (browser IDE)
codeserver_status="not running"
if systemctl is-active --quiet code-server@devuser 2>/dev/null; then
    codeserver_status="running on :8080"
fi
check "code-server" "$codeserver_status" "curl -sf -o /dev/null http://localhost:8080/healthz"

# VS Code Tunnel
tunnel_status="not configured"
if systemctl --user is-active --quiet code-tunnel 2>/dev/null; then
    tunnel_status="connected"
elif command -v /usr/local/bin/code &>/dev/null; then
    tunnel_status="installed (not running)"
fi
check "VS Code Tunnel" "$tunnel_status" "systemctl --user is-active --quiet code-tunnel"
HEADER

    # Per-project health checks
    for manifest in "$@"; do
        local name project_path
        name=$(manifest_get "$manifest" ".name")
        project_path=$(manifest_get "$manifest" ".path")

        # Count total checks for this section (health checks + env var checks)
        local health_count=0 req_count=0 section_total=0
        health_count=$(yq eval '.health | length' "$manifest" 2>/dev/null)
        [[ "$health_count" == "null" ]] && health_count=0

        req_count=$(yq eval '.env.required | length' "$manifest" 2>/dev/null)
        [[ "$req_count" == "null" || -z "$req_count" ]] && req_count=0

        # Also check if env.file exists — only count env checks if it does
        local env_file
        env_file=$(manifest_get "$manifest" ".env.file")
        if [[ -z "$env_file" ]]; then
            req_count=0
        fi

        section_total=$(( health_count + req_count ))
        [[ "$section_total" == "0" ]] && continue

        cat <<PROJ

# ── ${name} ──
echo ""
echo "  \${bold}${name}\${reset}"
_checks_in_section=0
_section_total=${section_total}
PROJ

        for (( i = 0; i < health_count; i++ )); do
            local label check_cmd
            label=$(manifest_get "$manifest" ".health[$i].label")
            check_cmd=$(manifest_get "$manifest" ".health[$i].check")
            # Escape double quotes in the check command for safe embedding
            check_cmd="${check_cmd//\"/\\\"}"
            echo "check \"${label}\" \"healthy\" \"${check_cmd}\""
        done

        # Check required env vars
        if [[ "$req_count" != "0" ]]; then
            for (( i = 0; i < req_count; i++ )); do
                local var_name
                var_name=$(manifest_get "$manifest" ".env.required[$i]")
                cat <<ENVCHECK
if [[ -f "${project_path}/${env_file}" ]]; then
    check "${var_name}" "set" "grep -q '^${var_name}=.\+' '${project_path}/${env_file}'"
else
    check "${var_name}" "missing" "false"
fi
ENVCHECK
            done
        fi
    done

    # Board Stats section
    cat <<'STATS'

# ── Board Stats ──
echo ""
echo "  ${bold}Board Stats${reset}"
if [[ -f ~/.board/shaped_at ]]; then
    shaped_date=$(cat ~/.board/shaped_at | cut -c1-16 | tr 'T' ' ')
    if [[ -f ~/.board/first_push_at ]]; then
        _checks_in_section=0
        _section_total=3
        echo "  ├─ Shaped ............... ${shaped_date}"
        ((_checks_in_section++)) || true
        push_date=$(cat ~/.board/first_push_at | cut -c1-16 | tr 'T' ' ')
        echo "  ├─ First commit ......... ${push_date}"
        ((_checks_in_section++)) || true
        if [[ -f ~/.board/metrics.json ]]; then
            ttfc=$(grep -o '"time_to_first_commit_minutes": [0-9]*' ~/.board/metrics.json | grep -o '[0-9]*')
            echo "  └─ Time to first commit . ${ttfc} minutes"
        else
            echo "  └─ First commit ......... ${push_date}"
        fi
    else
        _checks_in_section=0
        _section_total=2
        echo "  ├─ Shaped ............... ${shaped_date}"
        ((_checks_in_section++)) || true
        echo "  └─ First commit ......... ${dim}(not yet)${reset}"
    fi
else
    echo "  ${dim}└─ No stats available${reset}"
fi
STATS

    # Summary footer with caching, easter eggs, version
    cat <<'FOOTER'

# ── Summary ──
echo ""
echo "  ${dim}$(printf '%.0s─' {1..35})${reset}"
total=$((pass + fail))
if (( fail == 0 )); then
    echo "  ${green}All checks passed (${total}/${total})${reset} ${green}✓${reset}"
else
    echo "  ${red}${pass}/${total} passed · ${fail} issue(s)${reset}"
fi

# Easter egg: wipeout on 3+ failures
if (( fail >= 3 )); then
    echo ""
    echo "  ${bold}wipeout${reset} — multiple issues detected"
    echo "  Run the fixes above, then check again."
fi

# Easter egg: first successful check welcome
if (( fail == 0 )) && [[ ! -f ~/.board/.first-check-done ]]; then
    echo ""
    echo "  Welcome aboard. Happy coding"
    mkdir -p ~/.board
    touch ~/.board/.first-check-done
fi

echo ""
echo "  ${dim}board v1.0.0${reset}"
echo ""

# Cache results for MOTD
mkdir -p ~/.board
cat > ~/.board/last-check << CACHE
TIMESTAMP=$(date -Iseconds)
TOTAL=$total
PASSED=$pass
FAILED=$fail
CACHE

if (( fail > 0 )); then
    exit 1
fi
FOOTER
}
