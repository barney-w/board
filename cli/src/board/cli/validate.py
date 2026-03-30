"""board smoke-test — deployment validation via SSH health checks."""

from __future__ import annotations

import asyncio

import typer

from board.core import config as cfg
from board.core.errors import SSHError
from board.ui import console as con

DEFAULT_LOCATION = "australiaeast"

# Tool checks to run on the remote VM
TOOL_CHECKS = [
    "git --version",
    "python3 --version",
    "uv --version",
    "node --version",
    "npm --version",
    "docker --version",
    "docker compose version",
    "az version --query '\"azure-cli\"' -o tsv",
    "just --version",
    "nvim --version | head -1",
    "gh --version | head -1",
    "jq --version",
    "pnpm --version",
    "yq --version",
]

SSHD_SETTINGS = [
    "PermitRootLogin no",
    "PasswordAuthentication no",
    "X11Forwarding no",
    "MaxAuthTries 3",
]

CLOUD_INIT_ARTIFACTS = [
    ("test -x ~/setup-me.sh", "setup-me.sh exists and is executable"),
    ("test -f ~/.board/config", ".board/config exists"),
    (
        "stat -c '%U' /home/devuser 2>/dev/null | grep -q devuser "
        "|| ls -ld /home/devuser | grep -q devuser",
        "/home/devuser owned by devuser",
    ),
    (
        "test -f ~/.config/systemd/user/board-check.timer",
        "board-check systemd timer installed",
    ),
]


async def _run_smoke_test(
    name: str = "",
    hostname: str = "",
    key_path_override: str = "",
) -> None:
    """Run smoke tests against a remote VM."""
    if not hostname and name:
        hostname = cfg.hostname(name, DEFAULT_LOCATION)

    if not hostname:
        con.error("No hostname specified. Provide --name or --hostname.")
        return

    key_path = key_path_override or str(cfg.ssh_key_path_expanded(name)) if name else ""

    con.header(f"Board Smoke Test: {hostname}")

    from board.ssh.session import SSHSession

    passed = 0
    failed = 0

    async def run_remote(cmd: str) -> tuple[bool, str]:
        """Run a command on the remote and return (success, output)."""
        async with SSHSession() as ssh:
            await ssh.connect(hostname, username="devuser", key_path=key_path or None)
            result = await ssh.run(cmd, check=False)
            ok = (result.exit_status == 0) if hasattr(result, "exit_status") else False
            raw = result.stdout if hasattr(result, "stdout") else b""
            stdout = (raw.decode() if isinstance(raw, bytes) else (raw or "")).strip()
            return ok, stdout

    # ── Connectivity ──
    con.info("Connecting to board...")
    try:
        ok, _ = await run_remote("true")
        if ok:
            con.success("Connected")
        else:
            con.error("Cannot connect to board.")
            return
    except (SSHError, Exception) as exc:
        con.error(f"Cannot connect to board: {exc}")
        return

    # ── Cloud-init status ──
    con.info("Checking cloud-init status...")
    ok, ci_output = await run_remote("cloud-init status 2>/dev/null")
    # Normalize: newer cloud-init outputs just "done", older outputs "status: done"
    import re

    ci_match = re.search(r"(running|done|error|degraded|disabled)", ci_output)
    ci_status = ci_match.group(1) if ci_match else "unknown"

    if ci_status == "running":
        con.warn("Cloud-init is still running. Wait for it to finish first.")
        con.info("  Run: board vm ssh <name>, then: cloud-init status --wait")
        return
    elif ci_status in ("error", "degraded"):
        con.warn("Cloud-init reported errors. Some checks may fail.")
    elif ci_status == "done":
        con.success("Cloud-init complete")
    else:
        con.warn("Could not determine cloud-init status. Proceeding anyway.")

    # ── Tool checks ──
    con.info("Checking tools...")
    for cmd in TOOL_CHECKS:
        ok, output = await run_remote(cmd)
        if ok:
            con.success(f"{cmd} -> {output}")
            passed += 1
        else:
            con.error(f"{cmd} -> FAILED")
            failed += 1

    # ── Docker without sudo ──
    con.info("Checking Docker runs without sudo...")
    ok, _ = await run_remote("docker run --rm hello-world")
    if ok:
        con.success("Docker runs without sudo")
        passed += 1
    else:
        con.error("Docker requires sudo or is not working")
        failed += 1

    # ── SSH hardening ──
    con.info("Checking SSH hardening...")
    ok, sshd_config = await run_remote("sudo cat /etc/ssh/sshd_config")
    for setting in SSHD_SETTINGS:
        if f"^{setting}" in sshd_config or setting in sshd_config:
            con.success(setting)
            passed += 1
        else:
            con.error(f"{setting} NOT FOUND")
            failed += 1

    # ── Cloud-init artifacts ──
    con.info("Checking cloud-init artifacts...")
    for check_cmd, description in CLOUD_INIT_ARTIFACTS:
        ok, _ = await run_remote(check_cmd)
        if ok:
            con.success(description)
            passed += 1
        else:
            con.error(description)
            failed += 1

    # ── Project health (if provisioned) ──
    con.info("Checking project health...")
    ok, _ = await run_remote("test -f ~/projects/.board/check.sh")
    if ok:
        ok, check_output = await run_remote("bash ~/projects/.board/check.sh")
        if check_output:
            for line in check_output.split("\n"):
                con.info(f"  {line}")
            # Count results from output
            check_pass = check_output.count("\u2713")
            check_fail = check_output.count("\u2717")
            passed += check_pass
            failed += check_fail
    else:
        con.info("No project provisioning detected (check script not found)")

    # ── Summary ──
    con.divider()
    if failed == 0:
        con.success(f"All checks passed ({passed} passed, {failed} failed)")
    else:
        con.error(f"Results: {passed} passed, {failed} failed")


def smoke_test_command(
    name: str = typer.Argument("", help="Developer name (e.g. jbloggs)."),
    hostname: str = typer.Option("", "--hostname", help="Direct hostname override."),
    key_path: str = typer.Option("", "--key", help="SSH key path override."),
) -> None:
    """Run smoke tests against a deployed board."""
    asyncio.run(_run_smoke_test(name=name, hostname=hostname, key_path_override=key_path))
