"""Cloud-init wait logic — ported from scripts/lib/azure.sh wait_for_cloud_init().

Two-phase approach:
  Phase 1: Wait for SSH connectivity (hostname, then IP fallback)
  Phase 2: Wait for cloud-init to complete (status polling + marker file)
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import TYPE_CHECKING

from board.core.errors import SSHError

if TYPE_CHECKING:
    from board.ui.console import Console


async def wait_for_cloud_init(
    hostname: str,
    key_path: str,
    user: str = "devuser",
    fallback_ip: str = "",
    max_wait: int = 1800,
    console: Console | None = None,
) -> str:
    """Wait for cloud-init to complete on a newly deployed VM.

    Args:
        hostname: VM FQDN.
        key_path: Path to SSH private key.
        user: SSH username.
        fallback_ip: IP address to try if hostname DNS hasn't propagated.
        max_wait: Maximum wait time in seconds (default 30 minutes).
        console: Optional console for output.

    Returns:
        The SSH target that was successfully connected to (hostname or IP).

    Raises:
        SSHError: If SSH connectivity or cloud-init completion fails.
    """
    from board.ssh.session import SSHSession

    start_time = asyncio.get_event_loop().time()

    def elapsed() -> str:
        e = int(asyncio.get_event_loop().time() - start_time)
        return f"{e // 60}m {e % 60}s"

    def elapsed_secs() -> float:
        return asyncio.get_event_loop().time() - start_time

    # Clear stale host keys for redeployed VMs
    for target in [hostname, fallback_ip]:
        if target:
            subprocess.run(
                ["ssh-keygen", "-R", target],
                capture_output=True,
                check=False,
            )

    # ── Phase 1: Wait for SSH connectivity ──
    ssh_target = ""

    while elapsed_secs() < max_wait:
        for target in [hostname, fallback_ip]:
            if not target:
                continue
            try:
                async with SSHSession() as ssh:
                    await ssh.connect(target, username=user, key_path=key_path)
                    await ssh.run("true", check=False)
                ssh_target = target
                if console:
                    is_ip = target == fallback_ip and target != hostname
                    suffix = " via IP" if is_ip else ""
                    console.success(f"VM accepting SSH connections{suffix} ({elapsed()})")
                    if is_ip:
                        console.info(f"DNS for {hostname} may still be propagating")
                break
            except Exception:
                continue

        if ssh_target:
            break
        await asyncio.sleep(10)

    if not ssh_target:
        if console:
            console.error(f"VM did not become reachable after {elapsed()}")
            console.info("Check VM status: board vm ls")
        raise SSHError(f"VM {hostname} not reachable after {max_wait}s")

    # ── Phase 2: Wait for cloud-init completion ──
    if console:
        console.info("Now installing Docker, Python, Node.js, and dev tools.")
        console.info("This usually takes 5-8 minutes.")

    stale_done_count = 0
    marker_seen = False

    while elapsed_secs() < max_wait:
        try:
            async with SSHSession() as ssh:
                await ssh.connect(ssh_target, username=user, key_path=key_path)

                # Check cloud-init status
                result = await ssh.run(
                    "timeout 10 cloud-init status 2>/dev/null || echo 'status: unknown'",
                    check=False,
                )
                ci_output = result.stdout or "status: unknown"

                # Check marker file
                marker_result = await ssh.run(
                    f"test -f /home/{user}/.cloud-init-complete",
                    check=False,
                )
                has_marker = marker_result.exit_status == 0
                if has_marker:
                    marker_seen = True

                # ── Fast path: marker exists ──
                if marker_seen:
                    verify = await ssh.run(
                        "timeout 10 bash -lc 'which docker node python3'",
                        check=False,
                    )
                    if verify.exit_status == 0:
                        if "status: error" in ci_output:
                            if console:
                                console.warn(
                                    f"Cloud-init had errors but bootstrap completed ({elapsed()})"
                                )
                                console.info(
                                    "Some non-critical installs may have failed. "
                                    "Run: board smoke-test <name>"
                                )
                        else:
                            if console:
                                console.success(f"Cloud-init complete ({elapsed()})")
                        return ssh_target

                    stale_done_count += 1
                    if stale_done_count >= 3:
                        if console:
                            console.warn(
                                f"Cloud-init marker present but tool verify timed out ({elapsed()})"
                            )
                            console.info(
                                "Proceeding — provision engine will do full validation next."
                            )
                        return ssh_target

                elif "status: done" in ci_output:
                    # cloud-init done but no marker — stale from prior boot
                    stale_done_count += 1
                    if stale_done_count >= 6:
                        if console:
                            console.error(
                                f"Cloud-init reports 'done' but marker file is missing ({elapsed()})"
                            )
                            console.info(
                                "This usually means cloud-init ran on a previous boot "
                                "but failed on this one."
                            )
                            console.info(
                                "Debug: board vm ssh <name>, then: sudo cloud-init status --long"
                            )
                        raise SSHError("Cloud-init marker missing despite 'done' status")

                elif "status: error" in ci_output and not has_marker:
                    if console:
                        console.error("Cloud-init failed before completing bootstrap")
                        detail = await ssh.run(
                            "timeout 10 cloud-init status --long 2>/dev/null",
                            check=False,
                        )
                        if detail.stdout:
                            for line in detail.stdout.strip().split("\n"):
                                console.info(f"  {line}")
                        console.info(
                            "View log: board vm ssh <name>, then: "
                            "sudo tail -50 /var/log/cloud-init-output.log"
                        )
                    raise SSHError("Cloud-init failed")

                elif "status: running" in ci_output:
                    stale_done_count = 0  # Reset when actively running

                # Show progress from cloud-init log
                if console:
                    progress_result = await ssh.run(
                        "tail -5 /var/log/cloud-init-output.log 2>/dev/null "
                        "| grep -v '^$' | tail -1 | tr -cd '[:print:] ' | cut -c1-80",
                        check=False,
                    )
                    progress = progress_result.stdout.strip() if progress_result.stdout else ""
                    if not progress:
                        progress = "Installing development tools..."
                    if any(w in progress.lower() for w in ["complete", "ready for development"]):
                        progress = "Finalising installation..."
                    console.info(f"  {progress} ({elapsed()})")

        except SSHError:
            raise
        except Exception:
            pass  # SSH flakiness during cloud-init is expected

        await asyncio.sleep(10)

    # Absolute timeout
    if console:
        console.error("Cloud-init still running after 30 minutes")
    raise SSHError(f"Cloud-init timed out after {max_wait}s")
