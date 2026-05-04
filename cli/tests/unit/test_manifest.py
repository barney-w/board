"""Tests for manifest loading and file generators."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from board.core.manifest import (
    generate_check_script,
    generate_systemd_unit,
    generate_vscode_launch,
    generate_vscode_settings,
    generate_vscode_tasks,
    generate_workspace,
    list_projects,
    load,
    load_all,
)
from board.models.manifest import ProjectManifest

if TYPE_CHECKING:
    from pathlib import Path

# ── Loading ──────────────────────────────────────────────────────────────────


class TestLoad:
    def test_load_surf(self, surf_manifest_path: Path) -> None:
        m = load(surf_manifest_path)
        assert isinstance(m, ProjectManifest)
        assert m.name == "surf"
        assert m.description == "AI platform (Python/FastAPI + Postgres)"
        assert m.project_path == "~/projects/surf"
        assert len(m.services) == 1
        assert len(m.health) == 3

    def test_load_surf_kit(self, surf_kit_manifest_path: Path) -> None:
        m = load(surf_kit_manifest_path)
        assert m.name == "surf-kit"
        assert m.requires.tools == ["node", "pnpm"]
        assert m.docker is None
        assert len(m.health) == 2


class TestLoadAll:
    def test_load_all_unfiltered(self, fixtures_dir: Path) -> None:
        manifests = load_all(fixtures_dir)
        names = [m.name for m in manifests]
        assert "surf" in names
        assert "surf-kit" in names

    def test_load_all_filtered(self, fixtures_dir: Path) -> None:
        manifests = load_all(fixtures_dir, filter_names=["surf"])
        assert len(manifests) == 1
        assert manifests[0].name == "surf"

    def test_load_all_no_match(self, fixtures_dir: Path) -> None:
        manifests = load_all(fixtures_dir, filter_names=["nonexistent"])
        assert manifests == []

    def test_load_all_orders_dependencies(self, tmp_path: Path) -> None:
        (tmp_path / "atlas.project.yaml").write_text(
            "name: atlas\n"
            "repo: https://github.com/example/atlas\n"
            "dependencies: [surf-kit]\n"
        )
        (tmp_path / "surf-kit.project.yaml").write_text(
            "name: surf-kit\n"
            "repo: https://github.com/example/surf-kit\n"
        )

        manifests = load_all(tmp_path, filter_names=["atlas"])

        assert [manifest.name for manifest in manifests] == ["surf-kit", "atlas"]


class TestListProjects:
    def test_list(self, fixtures_dir: Path) -> None:
        projects = list_projects(fixtures_dir)
        names = [name for name, _ in projects]
        assert "surf" in names
        assert "surf-kit" in names

    def test_descriptions(self, fixtures_dir: Path) -> None:
        projects = list_projects(fixtures_dir)
        desc_map = dict(projects)
        assert desc_map["surf"] == "AI platform (Python/FastAPI + Postgres)"
        assert desc_map["surf-kit"] == "Component library (React/pnpm)"


# ── Systemd unit ─────────────────────────────────────────────────────────────


class TestGenerateSystemdUnit:
    def test_surf_api_unit(self, surf_manifest_path: Path) -> None:
        m = load(surf_manifest_path)
        service = m.services[0]
        unit = generate_systemd_unit(service, m.project_path)

        assert "[Unit]" in unit
        assert "Description=Surf API server" in unit
        assert "After=default.target docker.service" in unit

        assert "[Service]" in unit
        assert "Type=simple" in unit
        assert (
            "ExecStart=~/projects/surf/api/.venv/bin/uvicorn "
            "src.main:app --host 0.0.0.0 --port 8090"
        ) in unit
        assert "WorkingDirectory=~/projects/surf/api" in unit
        assert "EnvironmentFile=~/projects/surf/.env" in unit
        assert (
            "Environment=PATH=~/projects/surf/api/.venv/bin:/usr/local/bin:/usr/bin:/bin"
        ) in unit
        assert "Restart=on-failure" in unit
        assert "RestartSec=5" in unit

        assert "[Install]" in unit
        assert "WantedBy=default.target" in unit

    def test_no_env_file_or_extra_path(self) -> None:
        """When env_file and extra_path are empty, those lines are omitted."""
        from board.models.manifest import Service

        svc = Service(
            name="bare",
            description="Bare service",
            **{"exec": "/usr/bin/app"},
            working_dir=".",
        )
        unit = generate_systemd_unit(svc, "/opt/project")
        assert "EnvironmentFile" not in unit
        assert "Environment=PATH" not in unit


# ── VS Code tasks ────────────────────────────────────────────────────────────


class TestGenerateVscodeTasks:
    def test_surf_tasks(self, surf_manifest_path: Path) -> None:
        m = load(surf_manifest_path)
        raw = generate_vscode_tasks(m)
        obj = json.loads(raw)

        assert obj["version"] == "2.0.0"
        assert len(obj["tasks"]) == 5

        labels = [t["label"] for t in obj["tasks"]]
        assert "Dev Server" in labels
        assert "Frontend" in labels
        assert "Health Check" in labels

        # All tasks have type shell and problemMatcher
        for t in obj["tasks"]:
            assert t["type"] == "shell"
            assert t["problemMatcher"] == []

        # background tasks
        dev_task = next(t for t in obj["tasks"] if t["label"] == "Dev Server")
        assert dev_task["isBackground"] is True
        assert dev_task["command"] == "just dev"

        frontend_task = next(t for t in obj["tasks"] if t["label"] == "Frontend")
        assert frontend_task["isBackground"] is True

        # non-background task should not have isBackground
        health_task = next(t for t in obj["tasks"] if t["label"] == "Health Check")
        assert "isBackground" not in health_task

    def test_surf_kit_tasks_with_group(self, surf_kit_manifest_path: Path) -> None:
        m = load(surf_kit_manifest_path)
        raw = generate_vscode_tasks(m)
        obj = json.loads(raw)

        build_task = next(t for t in obj["tasks"] if t["label"] == "Build")
        assert build_task["group"] == "build"

        # Tasks without group should not have the key
        lint_task = next(t for t in obj["tasks"] if t["label"] == "Lint")
        assert "group" not in lint_task


# ── VS Code launch ───────────────────────────────────────────────────────────


class TestGenerateVscodeLaunch:
    def test_surf_launch(self, surf_manifest_path: Path) -> None:
        m = load(surf_manifest_path)
        raw = generate_vscode_launch(m)
        obj = json.loads(raw)

        assert obj["version"] == "0.2.0"
        assert len(obj["configurations"]) == 1

        cfg = obj["configurations"][0]
        assert cfg["name"] == "Debug Surf API"
        assert cfg["type"] == "debugpy"
        assert cfg["request"] == "launch"
        assert cfg["module"] == "uvicorn"
        assert cfg["args"] == ["src.main:app", "--host", "0.0.0.0", "--port", "8090", "--reload"]
        assert cfg["cwd"] == "${workspaceFolder}/api"
        assert cfg["envFile"] == "${workspaceFolder}/.env"
        assert "preLaunchTask" not in cfg

    def test_surf_kit_no_launch(self, surf_kit_manifest_path: Path) -> None:
        m = load(surf_kit_manifest_path)
        raw = generate_vscode_launch(m)
        obj = json.loads(raw)
        assert obj["configurations"] == []


# ── VS Code settings ─────────────────────────────────────────────────────────


class TestGenerateVscodeSettings:
    def test_surf_settings(self, surf_manifest_path: Path) -> None:
        m = load(surf_manifest_path)
        raw = generate_vscode_settings(m)
        obj = json.loads(raw)
        assert obj["python.defaultInterpreterPath"] == "./api/.venv/bin/python"

    def test_surf_kit_settings(self, surf_kit_manifest_path: Path) -> None:
        m = load(surf_kit_manifest_path)
        raw = generate_vscode_settings(m)
        obj = json.loads(raw)
        assert obj["typescript.tsdk"] == "./node_modules/typescript/lib"


# ── Workspace ────────────────────────────────────────────────────────────────


class TestGenerateWorkspace:
    def test_workspace_structure(
        self, surf_manifest_path: Path, surf_kit_manifest_path: Path
    ) -> None:
        manifests = [load(surf_manifest_path), load(surf_kit_manifest_path)]
        raw = generate_workspace(manifests)
        obj = json.loads(raw)

        # Folders
        assert len(obj["folders"]) == 2
        assert obj["folders"][0]["path"] == "surf"
        assert obj["folders"][0]["name"] == "surf (AI platform (Python/FastAPI + Postgres))"
        assert obj["folders"][1]["path"] == "surf-kit"
        assert obj["folders"][1]["name"] == "surf-kit (Component library (React/pnpm))"

        # Settings
        settings = obj["settings"]
        assert settings["remote.autoForwardPortsSource"] == "process"
        assert settings["task.allowAutomaticTasks"] == "on"

        # Port attributes from both manifests
        ports = settings["remote.portsAttributes"]
        assert "8090" in ports
        assert ports["8090"]["label"] == "Surf API"
        assert ports["8090"]["onAutoForward"] == "notify"
        assert "3000" in ports
        assert ports["3000"]["label"] == "Surf Web"
        assert "3100" in ports
        assert ports["3100"]["onAutoForward"] == "silent"
        assert "5432" in ports
        assert ports["5432"]["label"] == "Postgres"
        assert ports["5432"]["onAutoForward"] == "silent"
        assert "5173" in ports
        assert ports["5173"]["label"] == "surf-kit dev server"


# ── Check script ─────────────────────────────────────────────────────────────


class TestGenerateCheckScript:
    def _generate_for_both(self, surf_manifest_path: Path, surf_kit_manifest_path: Path) -> str:
        manifests = [load(surf_manifest_path), load(surf_kit_manifest_path)]
        return generate_check_script(manifests)

    def test_shebang_and_strict_mode(
        self, surf_manifest_path: Path, surf_kit_manifest_path: Path
    ) -> None:
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        assert script.startswith("#!/usr/bin/env bash\n")
        assert "set -euo pipefail" in script

    def test_colour_variables(self, surf_manifest_path: Path, surf_kit_manifest_path: Path) -> None:
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        for var in ("green=", "red=", "yellow=", "bold=", "dim=", "sky=", "reset="):
            assert var in script

    def test_helper_functions(self, surf_manifest_path: Path, surf_kit_manifest_path: Path) -> None:
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        assert "check()" in script or "check() {" in script
        assert "check_with_hint()" in script or "check_with_hint() {" in script

    def test_system_health_section(
        self, surf_manifest_path: Path, surf_kit_manifest_path: Path
    ) -> None:
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        assert "Board Check" in script
        assert '"Docker"' in script
        assert '"Disk"' in script
        assert '"Memory"' in script
        assert '"code-server"' in script
        assert '"VS Code Tunnel"' in script

    def test_surf_health_checks(
        self, surf_manifest_path: Path, surf_kit_manifest_path: Path
    ) -> None:
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        # Surf project section
        assert "# \u2500\u2500 surf \u2500\u2500" in script
        # Postgres — Docker container, plain check (port doesn't match a service)
        assert 'check "Postgres" "healthy"' in script
        assert 'check_with_hint "Postgres"' not in script
        # Surf API — app service, check_with_hint with dev hint
        assert 'check_with_hint "Surf API" "healthy"' in script
        assert "run 'just dev' to start" in script
        # Alembic — no port, plain check
        assert 'check "Alembic migrations" "healthy"' in script

    def test_surf_kit_health_checks(
        self, surf_manifest_path: Path, surf_kit_manifest_path: Path
    ) -> None:
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        assert "# \u2500\u2500 surf-kit \u2500\u2500" in script
        assert 'check "Dependencies" "healthy"' in script
        assert 'check "Build" "healthy"' in script

    def test_env_var_checks(self, surf_manifest_path: Path, surf_kit_manifest_path: Path) -> None:
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        # surf has required env var ANTHROPIC_API_KEY
        assert "ANTHROPIC_API_KEY" in script
        assert "grep -q" in script

    def test_board_stats_section(
        self, surf_manifest_path: Path, surf_kit_manifest_path: Path
    ) -> None:
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        assert "Board Stats" in script
        assert "created_at" in script
        assert "first_push_at" in script

    def test_summary_section(self, surf_manifest_path: Path, surf_kit_manifest_path: Path) -> None:
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        assert "Summary" in script
        assert "All checks passed" in script
        assert "issues need attention" in script
        assert "Welcome aboard" in script
        assert "board v1.0.0" in script

    def test_section_totals(self, surf_manifest_path: Path, surf_kit_manifest_path: Path) -> None:
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        # surf: 3 health + 1 required env = 4
        assert "_section_total=4" in script
        # surf-kit: 2 health + 0 required env = 2
        assert "_section_total=2" in script

    def test_caching_block(self, surf_manifest_path: Path, surf_kit_manifest_path: Path) -> None:
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        assert "~/.board/last-check" in script
        assert "TIMESTAMP=" in script
        assert "PASSED=$pass" in script
        assert "FAILED=$fail" in script

    def test_single_project(self, surf_kit_manifest_path: Path) -> None:
        """A manifest with no env.required should still work."""
        manifests = [load(surf_kit_manifest_path)]
        script = generate_check_script(manifests)
        assert "#!/usr/bin/env bash" in script
        assert 'check "Dependencies" "healthy"' in script
        assert 'check "Build" "healthy"' in script
        # No env var checks for surf-kit
        assert "ANTHROPIC_API_KEY" not in script

    def test_health_checks_have_cd_prefix(
        self, surf_manifest_path: Path, surf_kit_manifest_path: Path
    ) -> None:
        """Health checks should cd into the project directory first."""
        script = self._generate_for_both(surf_manifest_path, surf_kit_manifest_path)
        # surf-kit checks should cd to project directory (~ replaced with $HOME)
        assert 'cd \\"$HOME/projects/surf-kit\\" && test -d node_modules' in script
        assert 'cd \\"$HOME/projects/surf-kit\\" && test -d packages/core/dist' in script
        # surf checks should also have cd prefix
        assert 'cd \\"$HOME/projects/surf\\" && docker exec surf-postgres' in script
        assert 'cd \\"$HOME/projects/surf\\" && curl -sf http://localhost:8090' in script
