"""Tests for the provisioning engine using FakeSSHSession."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from board.models.manifest import (
    DockerConfig,
    DockerContainer,
    EnvConfig,
    HealthCheck,
    InstallStep,
    ProjectManifest,
    Requires,
    Service,
    VscodeConfig,
    VscodeTask,
)
from board.provision.engine import ProvisionEngine


@dataclass
class FakeSSHResult:
    """Fake SSH command result."""

    stdout: str = ""
    stderr: str = ""
    exit_status: int = 0


@dataclass
class FakeSSHSession:
    """Records commands and returns canned responses for testing."""

    commands: list[str] = field(default_factory=list)
    responses: dict[str, FakeSSHResult] = field(default_factory=dict)
    uploads: list[tuple[str, str]] = field(default_factory=list)
    default_exit_status: int = 0

    async def run(self, command: str, check: bool = True) -> FakeSSHResult:
        self.commands.append(command)
        # Check for matching response patterns
        for pattern, result in self.responses.items():
            if pattern in command:
                return result
        return FakeSSHResult(exit_status=self.default_exit_status)

    async def upload(self, local_path: str, remote_path: str) -> None:
        self.uploads.append((local_path, remote_path))


def _make_surf_manifest() -> ProjectManifest:
    """Create a manifest similar to surf.project.yaml for testing."""
    return ProjectManifest(
        name="surf",
        description="AI platform",
        repo="https://github.com/barney-w/surf",
        path="~/projects/surf",
        requires=Requires(tools=["python3", "uv", "docker"], cloud_init=True),
        install=[
            InstallStep(label="API dependencies", run="cd api && uv sync"),
            InstallStep(label="Ingestion dependencies", run="cd ingestion && uv sync"),
        ],
        docker=DockerConfig(
            compose_file="docker-compose.yml",
            containers=[
                DockerContainer(
                    name="surf-postgres",
                    health_cmd="pg_isready -U surf -d surf",
                    health_interval=2,
                    health_timeout=5,
                ),
            ],
        ),
        post_docker=[
            InstallStep(
                label="Run database migrations", run="cd api && uv run alembic upgrade head"
            ),
        ],
        services=[
            Service(
                name="surf-api",
                description="Surf API server",
                exec_="api/.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8090",
                working_dir="api",
                env_file=".env",
                health_url="http://localhost:8090/api/v1/health",
                health_timeout=5,
            ),
        ],
        env=EnvConfig(
            file=".env",
            fallback=".env.example",
            keyvault_secrets={"ANTHROPIC_API_KEY": "anthropic-api-key"},
            hardcoded={"POSTGRES_HOST": "localhost"},
            required=["ANTHROPIC_API_KEY"],
        ),
        vscode=VscodeConfig(
            tasks=[VscodeTask(label="Restart API", command="systemctl --user restart surf-api")],
        ),
        health=[
            HealthCheck(
                label="Postgres", check="docker exec surf-postgres pg_isready -U surf -d surf"
            ),
        ],
    )


def _make_minimal_manifest() -> ProjectManifest:
    """Minimal manifest with no optional blocks."""
    return ProjectManifest(name="minimal")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch asyncio.sleep to be instant in all provision tests."""
    import asyncio

    async def _instant_sleep(_: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)


class TestPhaseValidate:
    @pytest.mark.asyncio
    async def test_all_tools_found_first_attempt(self) -> None:
        ssh = FakeSSHSession()
        # All tools found, cloud-init complete
        ssh.responses["command -v python3"] = FakeSSHResult(exit_status=0)
        ssh.responses["command -v uv"] = FakeSSHResult(exit_status=0)
        ssh.responses["command -v docker"] = FakeSSHResult(exit_status=0)
        ssh.responses["test -f /home/devuser/.cloud-init-complete"] = FakeSSHResult(exit_status=0)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        result = await engine.phase_validate()
        assert result.success
        assert not engine.errors

    @pytest.mark.asyncio
    async def test_missing_tool_all_attempts(self) -> None:
        ssh = FakeSSHSession()
        # All tools fail
        ssh.responses["command -v"] = FakeSSHResult(exit_status=1)
        ssh.responses["test -f /home/devuser/.cloud-init-complete"] = FakeSSHResult(exit_status=1)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        result = await engine.phase_validate()
        assert not result.success
        assert len(engine.errors) > 0

    @pytest.mark.asyncio
    async def test_no_requirements(self) -> None:
        ssh = FakeSSHSession()
        engine = ProvisionEngine(ssh=ssh, manifest=_make_minimal_manifest())
        result = await engine.phase_validate()
        assert result.success


class TestPhaseClone:
    @pytest.mark.asyncio
    async def test_clone_new_repo(self) -> None:
        ssh = FakeSSHSession()
        # Project dir doesn't exist → clone
        ssh.responses["test -d"] = FakeSSHResult(exit_status=1)
        ssh.responses["git clone"] = FakeSSHResult(exit_status=0)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        result = await engine.phase_clone()
        assert result.success
        # Verify clone command was run
        assert any("git clone" in cmd for cmd in ssh.commands)

    @pytest.mark.asyncio
    async def test_pull_existing_repo(self) -> None:
        ssh = FakeSSHSession()
        # Project dir exists → pull
        ssh.responses["test -d"] = FakeSSHResult(exit_status=0)
        ssh.responses["git pull"] = FakeSSHResult(exit_status=0)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        result = await engine.phase_clone()
        assert result.success

    @pytest.mark.asyncio
    async def test_clone_failure_is_fatal(self) -> None:
        ssh = FakeSSHSession()
        ssh.responses["test -d"] = FakeSSHResult(exit_status=1)
        ssh.responses["git clone"] = FakeSSHResult(exit_status=1)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        result = await engine.phase_clone()
        assert not result.success
        assert len(engine.errors) > 0

    @pytest.mark.asyncio
    async def test_ttfc_hook_installed(self) -> None:
        ssh = FakeSSHSession()
        ssh.responses["test -d"] = FakeSSHResult(exit_status=0)
        ssh.responses["git pull"] = FakeSSHResult(exit_status=0)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        await engine.phase_clone()
        assert any("pre-push" in cmd for cmd in ssh.commands)


class TestPhaseEnv:
    @pytest.mark.asyncio
    async def test_no_env_block(self) -> None:
        ssh = FakeSSHSession()
        engine = ProvisionEngine(ssh=ssh, manifest=_make_minimal_manifest())
        result = await engine.phase_env()
        assert result.success

    @pytest.mark.asyncio
    async def test_env_with_keyvault(self) -> None:
        ssh = FakeSSHSession()
        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest(), keyvault_name="test-kv")
        result = await engine.phase_env()
        assert result.success
        # Verify env script was created and run
        assert any("env-surf.sh" in cmd for cmd in ssh.commands)

    @pytest.mark.asyncio
    async def test_env_fallback(self) -> None:
        ssh = FakeSSHSession()
        ssh.responses["cp "] = FakeSSHResult(exit_status=0)
        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        result = await engine.phase_env()
        assert result.success


class TestPhaseInstall:
    @pytest.mark.asyncio
    async def test_install_steps(self) -> None:
        ssh = FakeSSHSession()
        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        result = await engine.phase_install()
        assert result.success
        # Two install steps should have been run
        install_cmds = [c for c in ssh.commands if "uv sync" in c]
        assert len(install_cmds) == 2

    @pytest.mark.asyncio
    async def test_no_install_steps(self) -> None:
        ssh = FakeSSHSession()
        engine = ProvisionEngine(ssh=ssh, manifest=_make_minimal_manifest())
        result = await engine.phase_install()
        assert result.success


class TestPhaseDocker:
    @pytest.mark.asyncio
    async def test_docker_compose_up(self) -> None:
        ssh = FakeSSHSession()
        ssh.responses["docker compose"] = FakeSSHResult(exit_status=0)
        ssh.responses["docker update"] = FakeSSHResult(exit_status=0)
        ssh.responses["docker exec"] = FakeSSHResult(exit_status=0)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        result = await engine.phase_docker()
        assert result.success

    @pytest.mark.asyncio
    async def test_no_docker_block(self) -> None:
        ssh = FakeSSHSession()
        engine = ProvisionEngine(ssh=ssh, manifest=_make_minimal_manifest())
        result = await engine.phase_docker()
        assert result.success


class TestPhaseVscode:
    @pytest.mark.asyncio
    async def test_vscode_config_written(self) -> None:
        ssh = FakeSSHSession()
        # No existing files
        ssh.responses["test -f"] = FakeSSHResult(exit_status=1)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        result = await engine.phase_vscode()
        assert result.success
        assert any("tasks.json" in cmd for cmd in ssh.commands)

    @pytest.mark.asyncio
    async def test_vscode_skip_existing_without_force(self) -> None:
        ssh = FakeSSHSession()
        # Files already exist
        ssh.responses["test -f"] = FakeSSHResult(exit_status=0)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest(), force=False)
        await engine.phase_vscode()
        # Should not have written any JSON content
        write_cmds = [c for c in ssh.commands if "TASKSEOF" in c]
        assert len(write_cmds) == 0

    @pytest.mark.asyncio
    async def test_vscode_overwrite_with_force(self) -> None:
        ssh = FakeSSHSession()
        ssh.responses["test -f"] = FakeSSHResult(exit_status=0)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest(), force=True)
        await engine.phase_vscode()
        write_cmds = [c for c in ssh.commands if "TASKSEOF" in c]
        assert len(write_cmds) == 1


class TestPhaseHealth:
    @pytest.mark.asyncio
    async def test_health_checks_pass(self) -> None:
        ssh = FakeSSHSession()
        ssh.responses["pg_isready"] = FakeSSHResult(exit_status=0)
        ssh.responses["grep -q"] = FakeSSHResult(exit_status=0)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        result = await engine.phase_health()
        assert result.success

    @pytest.mark.asyncio
    async def test_health_check_failure_is_warning(self) -> None:
        ssh = FakeSSHSession()
        ssh.responses["pg_isready"] = FakeSSHResult(exit_status=1)
        ssh.responses["grep -q"] = FakeSSHResult(exit_status=1)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        result = await engine.phase_health()
        # Health failures are warnings, not errors — phase still succeeds
        assert result.success
        assert len(engine.warnings) > 0


class TestWarningAccumulation:
    @pytest.mark.asyncio
    async def test_warnings_accumulate_across_phases(self) -> None:
        ssh = FakeSSHSession()
        # install steps fail (warning), health checks fail (warning)
        ssh.responses["bash -c"] = FakeSSHResult(exit_status=1)
        ssh.responses["pg_isready"] = FakeSSHResult(exit_status=1)
        ssh.responses["grep -q"] = FakeSSHResult(exit_status=1)
        # But clone succeeds, tools found, cloud-init done
        ssh.responses["test -d"] = FakeSSHResult(exit_status=0)
        ssh.responses["git pull"] = FakeSSHResult(exit_status=0)
        ssh.responses["command -v"] = FakeSSHResult(exit_status=0)
        ssh.responses["test -f /home/devuser/.cloud-init-complete"] = FakeSSHResult(exit_status=0)
        ssh.responses["docker compose"] = FakeSSHResult(exit_status=0)
        ssh.responses["docker update"] = FakeSSHResult(exit_status=0)
        ssh.responses["docker exec"] = FakeSSHResult(exit_status=0)
        ssh.responses["curl -sf"] = FakeSSHResult(exit_status=0)
        ssh.responses["systemctl"] = FakeSSHResult(exit_status=0)
        ssh.responses["test -f '"] = FakeSSHResult(exit_status=1)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        await engine.run_all()
        # Should have accumulated warnings from install + health
        assert len(engine.warnings) > 0


class TestRunAll:
    @pytest.mark.asyncio
    async def test_all_phases_run_on_success(self) -> None:
        ssh = FakeSSHSession()
        # Everything succeeds
        ssh.responses["command -v"] = FakeSSHResult(exit_status=0)
        ssh.responses["test -f /home/devuser/.cloud-init-complete"] = FakeSSHResult(exit_status=0)
        ssh.responses["test -d"] = FakeSSHResult(exit_status=0)
        ssh.responses["git pull"] = FakeSSHResult(exit_status=0)
        ssh.responses["docker compose"] = FakeSSHResult(exit_status=0)
        ssh.responses["docker update"] = FakeSSHResult(exit_status=0)
        ssh.responses["docker exec"] = FakeSSHResult(exit_status=0)
        ssh.responses["curl -sf"] = FakeSSHResult(exit_status=0)
        ssh.responses["systemctl"] = FakeSSHResult(exit_status=0)
        ssh.responses["pg_isready"] = FakeSSHResult(exit_status=0)
        ssh.responses["grep -q"] = FakeSSHResult(exit_status=0)
        ssh.responses["test -f '"] = FakeSSHResult(exit_status=1)  # No existing vscode files

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        phases = await engine.run_all()
        assert len(phases) == 9  # All 9 phases ran
        assert all(p.success for p in phases)

    @pytest.mark.asyncio
    async def test_stops_on_validate_failure(self) -> None:
        ssh = FakeSSHSession()
        ssh.responses["command -v"] = FakeSSHResult(exit_status=1)
        ssh.responses["test -f /home/devuser/.cloud-init-complete"] = FakeSSHResult(exit_status=1)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        phases = await engine.run_all()
        # Should only run phase 1 (validate)
        assert len(phases) == 1
        assert not phases[0].success

    @pytest.mark.asyncio
    async def test_stops_on_clone_failure(self) -> None:
        ssh = FakeSSHSession()
        ssh.responses["command -v"] = FakeSSHResult(exit_status=0)
        ssh.responses["test -f /home/devuser/.cloud-init-complete"] = FakeSSHResult(exit_status=0)
        ssh.responses["test -d"] = FakeSSHResult(exit_status=1)
        ssh.responses["git clone"] = FakeSSHResult(exit_status=1)

        engine = ProvisionEngine(ssh=ssh, manifest=_make_surf_manifest())
        phases = await engine.run_all()
        # Should run validate (pass) and clone (fail) then stop
        assert len(phases) == 2
        assert phases[0].success
        assert not phases[1].success
