"""Tests for CLI command registration and basic invocation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from board.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Strip ANSI escape codes from *text*."""
    return _ANSI_RE.sub("", text)


class TestCommandRegistration:
    """Verify all commands are registered and show in --help."""

    def test_app_help_lists_all_commands(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Top-level commands
        assert "up" in result.output
        assert "admin" in result.output
        assert "fleet" in result.output
        assert "init" in result.output
        assert "smoke-test" in result.output
        assert "export-pass" in result.output
        # Subcommand group
        assert "vm" in result.output

    def test_up_help(self) -> None:
        result = runner.invoke(app, ["up", "--help"])
        assert result.exit_code == 0
        output = _plain(result.output)
        assert "--dry-run" in output
        assert "--demo" in output
        assert "--non-interactive" in output
        assert "--env" in output
        assert "--location" in output
        assert "--region-short" in output

    def test_admin_help(self) -> None:
        result = runner.invoke(app, ["admin", "--help"])
        assert result.exit_code == 0
        output = result.output.lower()
        assert "admin" in output or "control panel" in output
        assert "mfa-setup" in output

    def test_admin_mfa_setup_help(self) -> None:
        result = runner.invoke(app, ["admin", "mfa-setup", "--help"])
        assert result.exit_code == 0
        assert "mfa" in result.output.lower()

    def test_fleet_help(self) -> None:
        result = runner.invoke(app, ["fleet", "--help"])
        assert result.exit_code == 0
        output = _plain(result.output)
        assert "--env" in output
        assert "--region-short" in output

    def test_init_help(self) -> None:
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        assert "detect" in result.output.lower() or "stack" in result.output.lower()

    def test_smoke_test_help(self) -> None:
        result = runner.invoke(app, ["smoke-test", "--help"])
        assert result.exit_code == 0
        output = _plain(result.output)
        assert "--hostname" in output
        assert "--key" in output

    def test_export_pass_help(self) -> None:
        result = runner.invoke(app, ["export-pass", "--help"])
        assert result.exit_code == 0
        output = _plain(result.output)
        assert "--env" in output
        assert "--region" in output

    def test_vm_help_lists_subcommands(self) -> None:
        result = runner.invoke(app, ["vm", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "stop" in result.output
        assert "ssh" in result.output
        assert "ls" in result.output
        assert "status" in result.output
        assert "delete" in result.output
        assert "keygen" in result.output

    def test_vm_start_help(self) -> None:
        result = runner.invoke(app, ["vm", "start", "--help"])
        assert result.exit_code == 0
        assert "NAME" in result.output or "name" in result.output.lower()

    def test_vm_stop_help(self) -> None:
        result = runner.invoke(app, ["vm", "stop", "--help"])
        assert result.exit_code == 0

    def test_vm_ssh_help(self) -> None:
        result = runner.invoke(app, ["vm", "ssh", "--help"])
        assert result.exit_code == 0

    def test_vm_ls_help(self) -> None:
        result = runner.invoke(app, ["vm", "ls", "--help"])
        assert result.exit_code == 0

    def test_vm_status_help(self) -> None:
        result = runner.invoke(app, ["vm", "status", "--help"])
        assert result.exit_code == 0

    def test_vm_delete_help(self) -> None:
        result = runner.invoke(app, ["vm", "delete", "--help"])
        assert result.exit_code == 0

    def test_vm_keygen_help(self) -> None:
        result = runner.invoke(app, ["vm", "keygen", "--help"])
        assert result.exit_code == 0


class TestInitDetection:
    """Test board init stack detection against fixture directories."""

    def test_python_uv_detection(self, tmp_path: Path) -> None:
        """Detect Python + uv from pyproject.toml with [tool.uv]."""
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nname = 'myapp'\n\n[tool.uv]\ndev-dependencies = []\n"
        )
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "Python (uv)" in result.output
        assert 'name: "' in result.output
        assert "uv sync" in result.output

    def test_python_pip_detection(self, tmp_path: Path) -> None:
        """Detect Python + pip from requirements.txt."""
        (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "Python (pip)" in result.output
        assert "FastAPI" in result.output

    def test_node_npm_detection(self, tmp_path: Path) -> None:
        """Detect Node.js + npm from package.json."""
        (tmp_path / "package.json").write_text(
            '{"name": "myapp", "dependencies": {"express": "^4"}}'
        )
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "Node.js (npm)" in result.output
        assert "Express" in result.output

    def test_node_pnpm_detection(self, tmp_path: Path) -> None:
        """Detect Node.js + pnpm."""
        (tmp_path / "package.json").write_text('{"name": "myapp", "dependencies": {"next": "^14"}}')
        (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: 9\n")
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "Node.js (pnpm)" in result.output
        assert "Next.js" in result.output

    def test_go_detection(self, tmp_path: Path) -> None:
        """Detect Go from go.mod."""
        (tmp_path / "go.mod").write_text("module example.com/myapp\n\ngo 1.22\n")
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "Go" in result.output
        assert "go mod download" in result.output

    def test_ruby_rails_detection(self, tmp_path: Path) -> None:
        """Detect Ruby + Rails from Gemfile."""
        (tmp_path / "Gemfile").write_text("source 'https://rubygems.org'\ngem 'rails'\n")
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "Ruby (bundler)" in result.output
        assert "Rails" in result.output

    def test_java_gradle_spring_detection(self, tmp_path: Path) -> None:
        """Detect Java + Gradle + Spring Boot."""
        (tmp_path / "build.gradle").write_text(
            "plugins { id 'org.springframework.boot' version '3.2.0' }\n"
        )
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "Java (gradle)" in result.output
        assert "Spring Boot" in result.output

    def test_docker_service_detection(self, tmp_path: Path) -> None:
        """Detect Docker Compose services."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'myapp'\n")
        (tmp_path / "docker-compose.yml").write_text(
            "services:\n  db:\n    image: postgres:16\n  cache:\n    image: redis:7\n"
        )
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "PostgreSQL" in result.output
        assert "Redis" in result.output

    def test_unknown_stack_exits_with_error(self, tmp_path: Path) -> None:
        """Empty directory produces an error."""
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 1
        assert "Could not detect" in result.output

    def test_manifest_has_required_sections(self, tmp_path: Path) -> None:
        """Generated manifest contains all key sections."""
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nname = 'webapp'\n\n[tool.uv]\ndev-dependencies = []\n"
        )
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        output = result.output
        assert "name:" in output
        assert "requires:" in output
        assert "install:" in output
        assert "services:" in output
        assert "health:" in output
