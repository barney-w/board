"""9-phase provisioning engine — ported from scripts/provision-engine.sh.

Provisions a single project on a remote VM via SSH.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol

from board.models.deployment import PhaseResult

if TYPE_CHECKING:
    from board.models.deployment import LlmConfig
    from board.models.manifest import ProjectManifest
    from board.ui.console import Console


class SSHRunner(Protocol):
    """Protocol for SSH command execution — allows injection of fakes for testing."""

    async def run(self, command: str, check: bool = True) -> object: ...
    async def upload(self, local_path: str, remote_path: str) -> None: ...


# ── TTFC pre-push hook content ──

TTFC_HOOK = r"""#!/usr/bin/env bash
# Board: Time to First Commit measurement (one-time, self-removing)
if [[ -f ~/.board/created_at ]] && [[ ! -f ~/.board/first_push_at ]]; then
    date -Iseconds > ~/.board/first_push_at
    created=$(date -d "$(cat ~/.board/created_at)" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "$(cat ~/.board/created_at | cut -c1-19)" +%s 2>/dev/null || echo 0)
    pushed=$(date -d "$(cat ~/.board/first_push_at)" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "$(cat ~/.board/first_push_at | cut -c1-19)" +%s 2>/dev/null || echo 0)
    if (( created > 0 && pushed > 0 )); then
        delta=$(( (pushed - created) / 60 ))
        cat > ~/.board/metrics.json << METRICS
{
  "time_to_first_commit_minutes": $delta,
  "created_at": "$(cat ~/.board/created_at)",
  "first_push_at": "$(cat ~/.board/first_push_at)",
  "board_version": "2.0.0"
}
METRICS
        echo ""
        echo "  First push! Time to first commit: ${delta} minutes"
        echo ""
    fi
    # Self-remove from all project hooks
    find ~/projects -name "pre-push" -path "*/.git/hooks/*" -exec grep -l "Board: Time to First Commit" {} \; | xargs rm -f 2>/dev/null
fi
"""


class ProvisionEngine:
    """Provisions a single project on a remote VM through 9 phases.

    Constructor injection for SSH session, console, and optional KeyVault.
    Accumulates warnings and errors throughout all phases.
    """

    def __init__(
        self,
        ssh: SSHRunner,
        manifest: ProjectManifest,
        console: Console | None = None,
        keyvault_name: str = "",
        user: str = "devuser",
        force: bool = False,
        quiet: bool = False,
        llm_config: LlmConfig | None = None,
    ) -> None:
        self.ssh = ssh
        self.manifest = manifest
        self.console = console
        self.kv_name = keyvault_name
        self.user = user
        self.force = force
        self.quiet = quiet
        self.llm_config = llm_config
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.phases: list[PhaseResult] = []

        # Resolve project path (expand ~ to /home/user)
        path = manifest.project_path
        self.project_path = path.replace("~", f"/home/{user}")

    # ── Helpers ──

    def _step(self, phase: int, text: str) -> None:
        if self.console and not self.quiet:
            self.console.step(phase, 9, text)

    def _success(self, text: str) -> None:
        if self.console:
            self.console.success(text)

    def _warn(self, text: str) -> None:
        self.warnings.append(text)
        if self.console:
            self.console.warn(text)

    def _error(self, text: str) -> None:
        self.errors.append(text)
        if self.console:
            self.console.error(text)

    def _info(self, text: str) -> None:
        if self.console and not self.quiet:
            self.console.info(text)

    async def _run(self, cmd: str, check: bool = False) -> object:
        return await self.ssh.run(cmd, check=check)

    async def _run_ok(self, cmd: str) -> bool:
        """Run command, return True if exit code 0."""
        result = await self.ssh.run(cmd, check=False)
        return getattr(result, "exit_status", getattr(result, "returncode", 1)) == 0

    async def _run_output(self, cmd: str) -> str:
        """Run command, return stdout."""
        result = await self.ssh.run(cmd, check=False)
        return getattr(result, "stdout", "") or ""

    # ── Phase execution ──

    async def run_all(self) -> list[PhaseResult]:
        """Execute all 9 phases. Returns list of PhaseResult."""
        if self.console and not self.quiet:
            self.console.banner(
                "Board Provisioning Engine",
                f"Project: {self.manifest.name} -> {self.user}",
            )

        fatal = False

        phase_result = await self.phase_validate()
        if not phase_result.success:
            self._error(f"Validation failed — cannot proceed with {self.manifest.name}")
            fatal = True

        if not fatal:
            phase_result = await self.phase_clone()
            if not phase_result.success:
                self._error(f"Clone failed — cannot proceed with {self.manifest.name}")
                fatal = True

        if not fatal:
            await self.phase_env()
            await self.phase_install()
            await self.phase_docker()
            await self.phase_post_docker()
            await self.phase_services()
            await self.phase_vscode()
            await self.phase_health()

        # Write board config on success
        if not fatal and not self.errors:
            await self._write_board_config()

        return self.phases

    async def _write_board_config(self) -> None:
        """Write ~/.board/config and created_at timestamp."""
        await self._run(
            f"sudo mkdir -p /home/{self.user}/.board && "
            f"sudo chown {self.user}:{self.user} /home/{self.user}/.board"
        )
        config_script = (
            "cat > ~/.board/config << 'EOF'\n"
            "BOARD_NAME=board-$(hostname | sed 's/^vm-[a-z]*-[a-z]*-devvm-//')\n"
            "BOARD_REGION=$(curl -sf -H Metadata:true "
            "'http://169.254.169.254/metadata/instance/compute/location"
            "?api-version=2021-02-01&format=text' 2>/dev/null || echo 'unknown')\n"
            "BOARD_SIZE=$(curl -sf -H Metadata:true "
            "'http://169.254.169.254/metadata/instance/compute/vmSize"
            "?api-version=2021-02-01&format=text' 2>/dev/null || echo 'unknown')\n"
            "EOF"
        )
        if await self._run_ok(config_script):
            self._success("Board config written to ~/.board/config")
        else:
            self._warn("Could not write ~/.board/config")

        if await self._run_ok("date -Iseconds > ~/.board/created_at"):
            self._success("Recorded board creation timestamp")
        else:
            self._warn("Could not write ~/.board/created_at")

    def _record_phase(self, phase: int, name: str, success: bool, start: float) -> PhaseResult:
        result = PhaseResult(
            phase=phase,
            name=name,
            success=success,
            elapsed_seconds=time.monotonic() - start,
            warnings=list(self.warnings),
            errors=list(self.errors),
        )
        self.phases.append(result)
        return result

    # ── Phase 1: Validate requirements ──

    async def phase_validate(self) -> PhaseResult:
        self._step(1, "Validate requirements")
        start = time.monotonic()
        max_attempts = 6
        retry_delay = 15

        for attempt in range(1, max_attempts + 1):
            has_error = False
            is_final = attempt == max_attempts

            # Check required tools
            for tool in self.manifest.requires.tools:
                if await self._run_ok(f"command -v {tool}"):
                    if attempt == 1 or is_final:
                        self._success(f"{tool} found")
                else:
                    if is_final:
                        self._error(f"{tool} not found on VM")
                    has_error = True

            # Check cloud-init completion
            if self.manifest.requires.cloud_init:
                if await self._run_ok(f"test -f /home/{self.user}/.cloud-init-complete"):
                    if attempt == 1 or is_final:
                        self._success("cloud-init complete")
                else:
                    if is_final:
                        self._error("cloud-init has not completed (~/.cloud-init-complete missing)")
                    has_error = True

            if not has_error:
                if attempt > 1:
                    self._success(f"All tools ready (after {attempt} attempts)")
                    for tool in self.manifest.requires.tools:
                        self._success(f"{tool} found")
                return self._record_phase(1, "validate", True, start)

            if attempt < max_attempts:
                self._info(
                    f"Some tools not ready, retrying in {retry_delay}s "
                    f"(attempt {attempt}/{max_attempts}, cloud-init may still be running)..."
                )
                import asyncio

                await asyncio.sleep(retry_delay)

        return self._record_phase(1, "validate", False, start)

    # ── Phase 2: Clone repository ──

    async def phase_clone(self) -> PhaseResult:
        self._step(2, "Clone repository")
        start = time.monotonic()

        if await self._run_ok(f"test -d '{self.project_path}'"):
            if await self._run_ok(f"cd '{self.project_path}' && git pull"):
                self._success("Pulled latest changes")
            else:
                self._warn(f"git pull failed for {self.manifest.name}")
        else:
            if await self._run_ok(f"git clone '{self.manifest.repo}' '{self.project_path}'"):
                self._success(f"Cloned {self.manifest.repo}")
            else:
                self._error(f"Failed to clone {self.manifest.repo}")
                return self._record_phase(2, "clone", False, start)

        # Install TTFC pre-push hook
        await self._run(f"mkdir -p '{self.project_path}/.git/hooks'")
        hook_cmd = (
            f"cat > '{self.project_path}/.git/hooks/pre-push' << 'HOOKEOF'\n"
            f"{TTFC_HOOK}\nHOOKEOF\n"
            f"chmod +x '{self.project_path}/.git/hooks/pre-push'"
        )
        await self._run(hook_cmd)
        self._success("Installed TTFC pre-push hook")

        return self._record_phase(2, "clone", True, start)

    # ── Phase 3: Populate .env ──

    async def phase_env(self) -> PhaseResult:
        self._step(3, "Populate .env")
        start = time.monotonic()

        if not self.manifest.env or not self.manifest.env.file:
            self._info("No env block in manifest, skipping")
            return self._record_phase(3, "env", True, start)

        env_file = f"{self.project_path}/{self.manifest.env.file}"

        if self.kv_name:
            self._info(f"Generating env provisioning script (Key Vault: {self.kv_name})...")

            script_lines = [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f'ENV_FILE="{env_file}"',
                f'KV_NAME="{self.kv_name}"',
                'mkdir -p "$(dirname "$ENV_FILE")"',
                ': > "$ENV_FILE"',
                'if [[ -n "${KV_NAME:-}" ]]; then',
                "  logged_in=false",
                "  for attempt in $(seq 1 8); do",
                "    if az login --identity --allow-no-subscriptions 2>/dev/null; then",
                "      logged_in=true; break",
                "    fi",
                '    echo "  RBAC not ready, retrying in 15s (attempt $attempt/8)..."',
                "    sleep 15",
                "  done",
                "  if ! $logged_in; then",
                '    echo "ERROR: Failed to login with managed identity" >&2; exit 1',
                "  fi",
            ]

            for env_var, secret_name in self.manifest.env.keyvault_secrets.items():
                script_lines.append(
                    f'  secret_val=$(az keyvault secret show --vault-name "$KV_NAME" '
                    f'--name "{secret_name}" --query \'value\' -o tsv 2>/dev/null || echo "")'
                )
                script_lines.append(f'  echo "{env_var}=${{secret_val}}" >> "$ENV_FILE"')
                script_lines.append(
                    f'  [[ -z "$secret_val" ]] && echo "  WARNING: {env_var} is empty '
                    f'(secret \\"{secret_name}\\" not found in Key Vault)" >&2'
                )

            script_lines.append("fi")

            # Hardcoded values
            for key, val in self.manifest.env.hardcoded.items():
                script_lines.append(f'echo "{key}={val}" >> "$ENV_FILE"')

            script_content = "\n".join(script_lines) + "\n"

            await self._run("mkdir -p ~/projects/.board")
            # Upload script content via heredoc
            upload_cmd = (
                f"cat > ~/projects/.board/env-{self.manifest.name}.sh << 'ENVEOF'\n"
                f"{script_content}\nENVEOF"
            )
            await self._run(upload_cmd)

            if await self._run_ok(f"bash ~/projects/.board/env-{self.manifest.name}.sh"):
                self._success(".env populated via Key Vault")
            else:
                self._warn(
                    f"env provisioning script failed for {self.manifest.name} "
                    "— secrets may be incomplete"
                )
        else:
            # No Key Vault — use fallback
            fallback = self.manifest.env.fallback
            if fallback:
                self._info(f"No Key Vault specified, copying fallback ({fallback})...")
                src = f"{self.project_path}/{fallback}"
                if await self._run_ok(f"cp '{src}' '{env_file}'"):
                    self._success(f".env populated from fallback ({fallback})")
                else:
                    self._warn(f"Failed to copy {fallback} to {self.manifest.env.file}")
            else:
                self._info("No Key Vault and no fallback defined, skipping .env")

        # Append LLM-specific env vars (from setup wizard config)
        if self.llm_config and self.llm_config.provider != "none":
            env_lines: list[str] = []

            if self.llm_config.provider == "foundry":
                if self.llm_config.endpoint:
                    endpoint = self.llm_config.endpoint.rstrip("/")
                    env_lines.append(f"ANTHROPIC_FOUNDRY_BASE_URL={endpoint}/anthropic/")
                    env_lines.append(f"AZURE_OPENAI_ENDPOINT={endpoint}")
                if self.llm_config.api_key:
                    env_lines.append(f"ANTHROPIC_FOUNDRY_API_KEY={self.llm_config.api_key}")

            elif self.llm_config.provider == "anthropic":
                if self.llm_config.api_key:
                    env_lines.append(f"ANTHROPIC_API_KEY={self.llm_config.api_key}")

            if env_lines:
                # Only write vars that the manifest actually references
                manifest_vars = set()
                if self.manifest.env.keyvault_secrets:
                    manifest_vars.update(self.manifest.env.keyvault_secrets.keys())
                if self.manifest.env.hardcoded:
                    manifest_vars.update(self.manifest.env.hardcoded.keys())
                if self.manifest.env.required:
                    manifest_vars.update(self.manifest.env.required)

                filtered = [
                    line for line in env_lines
                    if line.split("=", 1)[0] in manifest_vars or not manifest_vars
                ]

                if filtered:
                    append_script = "\n".join(
                        f'echo "{line}" >> "{env_file}"' for line in filtered
                    )
                    if await self._run_ok(f"bash -c '{append_script}'"):
                        for line in filtered:
                            var_name = line.split("=", 1)[0]
                            self._success(f"{var_name} (from LLM config)")
                    else:
                        self._warn("Failed to append LLM env vars to .env")

        return self._record_phase(3, "env", True, start)

    # ── Phase 4: Install dependencies ──

    async def phase_install(self) -> PhaseResult:
        self._step(4, "Install dependencies")
        start = time.monotonic()

        if not self.manifest.install:
            self._info("No install steps defined, skipping")
            return self._record_phase(4, "install", True, start)

        for step in self.manifest.install:
            if await self._run_ok(f"cd '{self.project_path}' && bash -c '{step.run}'"):
                self._success(f"{step.label} done")
            else:
                self._warn(f"Install step '{step.label}' did not complete for {self.manifest.name}")

        return self._record_phase(4, "install", True, start)

    # ── Phase 5: Docker services ──

    async def phase_docker(self) -> PhaseResult:
        self._step(5, "Docker services")
        start = time.monotonic()

        if not self.manifest.docker:
            self._info("No docker block defined, skipping")
            return self._record_phase(5, "docker", True, start)

        compose_file = self.manifest.docker.compose_file
        if not await self._run_ok(
            f"cd '{self.project_path}' && docker compose -f '{compose_file}' up -d"
        ):
            self._warn(f"docker compose up failed for {self.manifest.name}")
            return self._record_phase(5, "docker", True, start)

        self._success("docker compose up")

        # Health polling for each container
        for container in self.manifest.docker.containers:
            if container.restart_policy:
                if await self._run_ok(
                    f"docker update --restart {container.restart_policy} {container.name}"
                ):
                    self._success(
                        f"{container.name} restart policy set to {container.restart_policy}"
                    )
                else:
                    self._warn(f"Failed to set restart policy for {container.name}")

            if container.health_cmd:
                import asyncio

                interval = container.health_interval
                timeout = container.health_timeout
                elapsed = 0
                healthy = False

                while elapsed < timeout:
                    if await self._run_ok(f"docker exec {container.name} {container.health_cmd}"):
                        self._success(f"{container.name} healthy")
                        healthy = True
                        break
                    await asyncio.sleep(interval)
                    elapsed += interval

                if not healthy:
                    self._warn(f"{container.name} did not become healthy within {timeout}s")

        return self._record_phase(5, "docker", True, start)

    # ── Phase 6: Post-Docker setup ──

    async def phase_post_docker(self) -> PhaseResult:
        self._step(6, "Post-Docker setup")
        start = time.monotonic()

        if not self.manifest.post_docker:
            self._info("No post-docker steps defined, skipping")
            return self._record_phase(6, "post_docker", True, start)

        for step in self.manifest.post_docker:
            if await self._run_ok(f"cd '{self.project_path}' && bash -c '{step.run}'"):
                self._success(f"{step.label} done")
            else:
                self._warn(
                    f"Post-docker step '{step.label}' did not complete for {self.manifest.name}"
                )

        return self._record_phase(6, "post_docker", True, start)

    # ── Phase 7: systemd user services ──

    async def phase_services(self) -> PhaseResult:
        self._step(7, "systemd user services")
        start = time.monotonic()

        if not self.manifest.services:
            self._info("No services defined, skipping")
            return self._record_phase(7, "services", True, start)

        from board.core.manifest import generate_systemd_unit

        dev_mode = self.manifest.dev is not None

        for svc in self.manifest.services:
            self._info(f"Setting up {svc.name}...")
            unit_content = generate_systemd_unit(svc, self.project_path)

            await self._run("mkdir -p ~/.config/systemd/user")
            # Upload unit file
            upload_cmd = (
                f"cat > ~/.config/systemd/user/{svc.name}.service << 'UNITEOF'\n"
                f"{unit_content}\nUNITEOF"
            )
            await self._run(upload_cmd)

            if dev_mode:
                # Dev mode: install unit but don't auto-start — developer runs
                # interactive commands (e.g. just dev) instead
                if await self._run_ok("systemctl --user daemon-reload"):
                    self._success(
                        f"{svc.name} unit installed "
                        f"(run '{self.manifest.dev.run}' or "  # type: ignore[union-attr]
                        f"'systemctl --user start {svc.name}' to start)"
                    )
                else:
                    self._warn(f"Failed to reload systemd units for {svc.name}")
                continue

            if await self._run_ok(
                f"systemctl --user daemon-reload && systemctl --user enable --now {svc.name}"
            ):
                self._success(f"{svc.name} enabled and started")
            else:
                self._warn(f"Failed to enable/start {svc.name}")
                continue

            # Health URL polling
            if svc.health_url:
                import asyncio

                timeout = svc.health_timeout
                elapsed = 0
                healthy = False

                while elapsed < timeout:
                    if await self._run_ok(f"curl -sf {svc.health_url}"):
                        self._success(f"{svc.name} health check passed")
                        healthy = True
                        break
                    await asyncio.sleep(2)
                    elapsed += 2

                if not healthy:
                    self._warn(
                        f"{svc.name} health check timed out after {timeout}s ({svc.health_url})"
                    )

        return self._record_phase(7, "services", True, start)

    # ── Phase 8: VS Code configuration ──

    async def phase_vscode(self) -> PhaseResult:
        self._step(8, "VS Code configuration")
        start = time.monotonic()

        if not self.manifest.vscode:
            self._info("No VS Code config defined, skipping")
            return self._record_phase(8, "vscode", True, start)

        from board.core.manifest import (
            generate_vscode_launch,
            generate_vscode_settings,
            generate_vscode_tasks,
        )

        vscode = self.manifest.vscode
        vscode_dir = f"{self.project_path}/.vscode"
        await self._run(f"mkdir -p '{vscode_dir}'")

        # Tasks
        if vscode.tasks:
            tasks_file = f"{vscode_dir}/tasks.json"
            if not self.force and await self._run_ok(f"test -f '{tasks_file}'"):
                self._info("tasks.json already exists (use --force to overwrite)")
            else:
                content = generate_vscode_tasks(self.manifest)
                await self._run(f"cat > '{tasks_file}' << 'TASKSEOF'\n{content}\nTASKSEOF")
                self._success("tasks.json written")

        # Launch
        if vscode.launch:
            launch_file = f"{vscode_dir}/launch.json"
            if not self.force and await self._run_ok(f"test -f '{launch_file}'"):
                self._info("launch.json already exists (use --force to overwrite)")
            else:
                content = generate_vscode_launch(self.manifest)
                await self._run(f"cat > '{launch_file}' << 'LAUNCHEOF'\n{content}\nLAUNCHEOF")
                self._success("launch.json written")

        # Settings
        if vscode.settings:
            settings_file = f"{vscode_dir}/settings.json"
            if not self.force and await self._run_ok(f"test -f '{settings_file}'"):
                self._info("settings.json already exists (use --force to overwrite)")
            else:
                content = generate_vscode_settings(self.manifest)
                await self._run(f"cat > '{settings_file}' << 'SETTINGSEOF'\n{content}\nSETTINGSEOF")
                self._success("settings.json written")

        return self._record_phase(8, "vscode", True, start)

    # ── Phase 9: Health check verification ──

    async def phase_health(self) -> PhaseResult:
        self._step(9, "Health check verification")
        start = time.monotonic()

        if self.manifest.health:
            for check in self.manifest.health:
                if await self._run_ok(f"cd '{self.project_path}' && bash -c '{check.check}'"):
                    self._success(f"{check.label}: passed")
                else:
                    self._warn(f"Health check '{check.label}' failed for {self.manifest.name}")
        else:
            self._info("No health checks defined, skipping")

        # Check required env vars
        if self.manifest.env and self.manifest.env.required and self.manifest.env.file:
            self._info("Checking required environment variables...")
            env_path = f"{self.project_path}/{self.manifest.env.file}"
            is_foundry = self.llm_config and self.llm_config.provider == "foundry"
            for var_name in self.manifest.env.required:
                # Foundry auth replaces direct API key — skip this check
                if var_name == "ANTHROPIC_API_KEY" and is_foundry:
                    self._info(f"{var_name} skipped (using Foundry credentials)")
                    continue
                if await self._run_ok(f"grep -q '^{var_name}=.\\+' '{env_path}'"):
                    self._success(f"{var_name} is set")
                else:
                    self._warn(
                        f"Required env var '{var_name}' is empty or missing in .env "
                        f"for {self.manifest.name}"
                    )

        # Summary
        if self.console and not self.quiet:
            self.console.divider()
            if self.errors:
                self.console.header(f"Errors ({len(self.errors)})")
                for err in self.errors:
                    self.console.error(err)
            if self.warnings:
                self.console.header(f"Warnings ({len(self.warnings)})")
                for warn in self.warnings:
                    self.console.warn(warn)
                self.console.info("Tip: Re-run with Key Vault name to populate missing secrets")
                self.console.info("Tip: Check systemd logs with: journalctl --user -u <service> -f")
            if not self.errors and not self.warnings:
                self._success(f"All checks passed for {self.manifest.name}")
            elif not self.errors:
                self._success(f"Provisioning completed with {len(self.warnings)} warning(s)")

        return self._record_phase(9, "health", True, start)
