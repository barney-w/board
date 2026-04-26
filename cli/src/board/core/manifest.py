"""Manifest loading and file generators — Python port of scripts/lib/manifest.sh."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from ruamel.yaml import YAML

from board.models.manifest import ProjectManifest, Service

if TYPE_CHECKING:
    from pathlib import Path

# ── YAML loading ────────────────────────────────────────────────────────────


def load(path: Path) -> ProjectManifest:
    """Load a single .project.yaml file."""
    yaml = YAML()
    data = yaml.load(path)
    return ProjectManifest(**data)


def load_all(
    directory: Path,
    filter_names: list[str] | None = None,
) -> list[ProjectManifest]:
    """Load all .project.yaml files from a directory, optionally filtering by name."""
    manifests: list[ProjectManifest] = []
    for path in sorted(directory.glob("*.project.yaml")):
        manifest = load(path)
        if filter_names is None or manifest.name in filter_names:
            manifests.append(manifest)
    return manifests


def list_projects(directory: Path) -> list[tuple[str, str]]:
    """List all projects as (name, description) tuples."""
    results: list[tuple[str, str]] = []
    for path in sorted(directory.glob("*.project.yaml")):
        manifest = load(path)
        results.append((manifest.name, manifest.description))
    return results


# ── Systemd unit generation ─────────────────────────────────────────────────


def generate_systemd_unit(service: Service, project_path: str) -> str:
    """Generate a systemd user unit file for a service.

    Matches ``manifest_generate_systemd_unit()`` in manifest.sh.
    """
    lines = [
        "[Unit]",
        f"Description={service.description}",
        "After=default.target docker.service",
        "",
        "[Service]",
        "Type=simple",
        f"ExecStart={project_path}/{service.exec_}",
        f"WorkingDirectory={project_path}/{service.working_dir}",
    ]

    if service.env_file:
        lines.append(f"EnvironmentFile={project_path}/{service.env_file}")

    if service.extra_path:
        lines.append(
            f"Environment=PATH={project_path}/{service.extra_path}:/usr/local/bin:/usr/bin:/bin"
        )

    lines += [
        "Restart=on-failure",
        "RestartSec=5",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",  # trailing newline
    ]
    return "\n".join(lines)


# ── VS Code file generation ─────────────────────────────────────────────────


def generate_vscode_tasks(manifest: ProjectManifest) -> str:
    """Generate a .vscode/tasks.json file.

    Matches ``manifest_generate_vscode_tasks()`` in manifest.sh.
    """
    tasks_list: list[dict[str, Any]] = []

    if manifest.vscode:
        for task in manifest.vscode.tasks:
            entry: dict[str, Any] = {
                "label": task.label,
                "type": "shell",
                "command": task.command,
                "problemMatcher": [],
            }
            if task.background:
                entry["isBackground"] = True
            if task.group:
                entry["group"] = task.group
            tasks_list.append(entry)

    obj = {"version": "2.0.0", "tasks": tasks_list}
    return json.dumps(obj, indent=2) + "\n"


def generate_vscode_launch(manifest: ProjectManifest) -> str:
    """Generate a .vscode/launch.json file.

    Matches ``manifest_generate_vscode_launch()`` in manifest.sh.
    """
    configs: list[dict[str, Any]] = []

    if manifest.vscode:
        for lc in manifest.vscode.launch:
            entry: dict[str, Any] = {
                "name": lc.name,
                "type": lc.type,
                "request": lc.request,
                "module": lc.module,
                "args": lc.args,
            }
            if lc.cwd:
                entry["cwd"] = f"${{workspaceFolder}}/{lc.cwd}"
            if lc.env_file:
                entry["envFile"] = f"${{workspaceFolder}}/{lc.env_file}"
            if lc.pre_launch_task:
                entry["preLaunchTask"] = lc.pre_launch_task
            configs.append(entry)

    obj = {"version": "0.2.0", "configurations": configs}
    return json.dumps(obj, indent=2) + "\n"


def generate_vscode_settings(manifest: ProjectManifest) -> str:
    """Generate a .vscode/settings.json file.

    Matches ``manifest_generate_vscode_settings()`` in manifest.sh.
    """
    settings = manifest.vscode.settings if manifest.vscode else {}
    return json.dumps(settings, indent=2) + "\n"


# ── Workspace generation ────────────────────────────────────────────────────


def generate_workspace(manifests: list[ProjectManifest]) -> str:
    """Generate a board.code-workspace file.

    Matches ``manifest_generate_workspace()`` in manifest.sh.
    """
    folders: list[dict[str, str]] = []
    ports: dict[str, dict[str, str]] = {}

    for m in manifests:
        # Derive folder name from path (last component)
        rel_path = m.project_dir_name
        folder_name = f"{m.name} ({m.description})"
        folders.append({"path": rel_path, "name": folder_name})

        # Collect port attributes
        if m.vscode:
            for port_key, port_cfg in m.vscode.ports.items():
                ports[port_key] = {
                    "label": port_cfg.label,
                    "onAutoForward": port_cfg.auto_forward,
                }

    # Board-level services (always present, not project-specific)
    ports["9190"] = {"label": "Cockpit", "onAutoForward": "silent"}
    ports["9443"] = {"label": "Portainer", "onAutoForward": "silent"}

    obj = {
        "folders": folders,
        "settings": {
            "remote.portsAttributes": ports,
            "remote.autoForwardPortsSource": "process",
            "task.allowAutomaticTasks": "on",
        },
    }
    return json.dumps(obj, indent=2) + "\n"


# ── Quickstart generation ─────────────────────────────────────────────────


def generate_quickstart(manifests: list[ProjectManifest]) -> str:
    """Generate a QUICKSTART.md from project manifests.

    Shown automatically in VS Code when a developer connects to the VM.
    """
    lines: list[str] = [
        "# Quickstart",
        "",
        "Welcome to your dev VM. Here's how to get started.",
        "",
        "## System",
        "",
        "```bash",
        "# Health check — see what's running and what needs attention",
        "check",
        "```",
        "",
    ]

    for m in manifests:
        project_dir = m.project_dir_name
        lines.append(f"## {m.name}")
        lines.append("")
        lines.append(f"> {m.description}")
        lines.append("")

        # Key tasks — prefer dev workflow, then vscode tasks, then service commands
        tasks_to_show: list[tuple[str, str]] = []
        if m.dev:
            # Dev workflow — show interactive commands
            tasks_to_show.append((m.dev.description or "Start developing", m.dev.run))
            for task in m.dev.tasks:
                tasks_to_show.append((task.label, task.run))
        elif m.vscode and m.vscode.tasks:
            for vscode_task in m.vscode.tasks:
                # Replace VS Code variables with actual paths
                cmd = vscode_task.command.replace("${workspaceFolder}", f"~/projects/{project_dir}")
                tasks_to_show.append((vscode_task.label, cmd))

        # Services — only add log/restart if no dev or vscode tasks cover them
        if m.services and not m.dev and not (m.vscode and m.vscode.tasks):
            for svc in m.services:
                tasks_to_show.append(
                    (
                        f"View {svc.name} logs",
                        f"journalctl --user -u {svc.name} -f --no-hostname -o cat",
                    )
                )
                tasks_to_show.append(
                    (f"Restart {svc.name}", f"systemctl --user restart {svc.name}")
                )

        if tasks_to_show:
            lines.append("```bash")
            lines.append(f"cd ~/projects/{project_dir}")
            lines.append("")
            for label, cmd in tasks_to_show:
                lines.append(f"# {label}")
                lines.append(cmd)
                lines.append("")
            # Remove trailing blank line inside code block
            if lines[-1] == "":
                lines.pop()
            lines.append("```")
            lines.append("")

        # Ports
        if m.vscode and m.vscode.ports:
            lines.append("| Port | Service |")
            lines.append("|------|---------|")
            for port, cfg in m.vscode.ports.items():
                lines.append(f"| {port} | {cfg.label} |")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Auto-generated by Board from project manifests.*")
    lines.append("")

    return "\n".join(lines)


# ── Health check script generation ──────────────────────────────────────────

_CHECK_HEADER = r"""#!/usr/bin/env bash
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
_section_total=7

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

# Cockpit (system admin UI)
cockpit_status="not running"
if systemctl is-active --quiet cockpit.socket 2>/dev/null; then
    cockpit_status="socket active on :9190"
fi
check "Cockpit" "$cockpit_status" "systemctl is-active --quiet cockpit.socket"

# Portainer (Docker management UI)
portainer_status="not running"
if docker inspect --format='{{.State.Running}}' portainer 2>/dev/null | grep -q true; then
    portainer_status="running on :9443"
fi
check "Portainer" "$portainer_status" "docker inspect --format='{{.State.Running}}' portainer 2>/dev/null | grep -q true"
"""

_CHECK_STATS = r"""
# ── Board Stats ──
echo ""
echo "  ${bold}Board Stats${reset}"
if [[ -f ~/.board/created_at ]]; then
    created_date=$(cat ~/.board/created_at | cut -c1-16 | tr 'T' ' ')
    if [[ -f ~/.board/first_push_at ]]; then
        _checks_in_section=0
        _section_total=3
        echo "  ├─ Created ............... ${created_date}"
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
        echo "  ├─ Created ............... ${created_date}"
        ((_checks_in_section++)) || true
        echo "  └─ First commit ......... ${dim}(not yet)${reset}"
    fi
else
    echo "  ${dim}└─ No stats available${reset}"
fi
"""

_CHECK_FOOTER = r"""
# ── Summary ──
echo ""
echo "  ${dim}$(printf '%.0s─' {1..35})${reset}"
total=$((pass + fail))
if (( fail == 0 )); then
    echo "  ${green}All checks passed (${total}/${total})${reset} ${green}✓${reset}"
else
    echo "  ${red}${pass}/${total} passed · ${fail} issue(s)${reset}"
fi

# Warn on 3+ failures
if (( fail >= 3 )); then
    echo ""
    echo "  ${bold}${fail} issues need attention${reset} — run the fixes above, then check again."
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
"""


def generate_check_script(manifests: list[ProjectManifest]) -> str:
    """Generate a complete board health-check bash script.

    Matches ``manifest_generate_check_script()`` in manifest.sh.
    """
    parts: list[str] = [_CHECK_HEADER.lstrip("\n")]

    # Per-project health checks
    for m in manifests:
        project_path = m.project_path

        # Count total checks for this section
        health_count = len(m.health)
        env_file = m.env.file if m.env else ""
        req_count = len(m.env.required) if m.env and env_file else 0
        section_total = health_count + req_count

        if section_total == 0:
            continue

        # Build set of service ports — used to add dev hints on failure
        svc_ports: set[int] = set()
        dev_run = ""
        if m.dev and m.services:
            dev_run = m.dev.run
            for svc in m.services:
                if svc.health_url:
                    parsed = urlparse(svc.health_url)
                    if parsed.port:
                        svc_ports.add(parsed.port)

        # Section header
        parts.append(f"\n# \u2500\u2500 {m.name} \u2500\u2500")
        parts.append('echo ""')
        parts.append(f'echo "  ${{bold}}{m.name}${{reset}}"')
        parts.append("_checks_in_section=0")
        parts.append(f"_section_total={section_total}")

        # Health checks
        for hc in m.health:
            # Escape double quotes in the check command for safe embedding
            escaped_cmd = hc.check.replace('"', '\\"')
            shell_path = project_path.replace("~", "$HOME")
            if hc.port and hc.port in svc_ports:
                # App service check — show dev hint on failure
                hint = f"run '{dev_run}' to start"
                parts.append(
                    f'check_with_hint "{hc.label}" "healthy" "{hint}" '
                    f'"cd \\"{shell_path}\\" && {escaped_cmd}"'
                )
            else:
                parts.append(
                    f'check "{hc.label}" "healthy" "cd \\"{shell_path}\\" && {escaped_cmd}"'
                )

        # Required env var checks
        if req_count > 0:
            env_path = f"{project_path}/{env_file}".replace("~", "$HOME")
            for var_name in m.env.required:  # type: ignore[union-attr]
                parts.append(f'if [[ -f "{env_path}" ]]; then')
                parts.append(
                    f'    check "{var_name}" "set" "grep -q \'^{var_name}=.\\+\' \\"{env_path}\\""'
                )
                parts.append("else")
                parts.append(f'    check "{var_name}" "missing" "false"')
                parts.append("fi")

    parts.append(_CHECK_STATS.rstrip("\n"))
    parts.append(_CHECK_FOOTER.rstrip("\n"))
    parts.append("")  # final newline

    return "\n".join(parts)
