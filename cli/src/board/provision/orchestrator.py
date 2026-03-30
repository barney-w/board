"""Multi-project orchestrator — ported from scripts/provision-projects.sh.

Discovers manifests, provisions each project via ProvisionEngine,
then generates cross-project artifacts (workspace, check script, manifest copies).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from board.core.manifest import (
    generate_check_script,
    generate_workspace,
    load_all,
)
from board.provision.engine import ProvisionEngine, SSHRunner

if TYPE_CHECKING:
    from pathlib import Path

    from board.ui.console import Console


async def provision_projects(
    ssh: SSHRunner,
    manifest_dir: Path,
    console: Console | None = None,
    keyvault_name: str = "",
    user: str = "devuser",
    filter_names: list[str] | None = None,
    force: bool = False,
    quiet: bool = False,
) -> tuple[int, int]:
    """Discover and provision all projects.

    Args:
        ssh: SSH session for remote commands.
        manifest_dir: Directory containing *.project.yaml files.
        console: Optional console for output.
        keyvault_name: Optional Key Vault name for secret retrieval.
        user: SSH username.
        filter_names: Optional list of project names to filter by.
        force: Overwrite existing VS Code configs.
        quiet: Suppress visual output.

    Returns:
        Tuple of (success_count, fail_count).
    """
    start_time = time.monotonic()

    # Step 1: Discover manifests
    if console and not quiet:
        console.banner("Board Provisioner", f"Provisioning projects on {user}")
        console.step(1, 6, "Discover project manifests")

    manifests = load_all(manifest_dir, filter_names=filter_names)

    if not manifests:
        if console:
            console.error(f"No *.project.yaml files found in {manifest_dir}")
        return 0, 0

    for m in manifests:
        if console and not quiet:
            console.success(f"Found: {m.name}")
    if console and not quiet:
        console.info(f"Total: {len(manifests)} project(s)")

    # Step 2: Provision each project
    if console and not quiet:
        console.step(2, 6, "Provision projects")

    results: list[tuple[str, bool]] = []
    provisioned = []

    for m in manifests:
        if console and not quiet:
            console.header(m.name)

        engine = ProvisionEngine(
            ssh=ssh,
            manifest=m,
            console=console,
            keyvault_name=keyvault_name,
            user=user,
            force=force,
            quiet=quiet,
        )

        try:
            phases = await engine.run_all()
            success = all(p.success for p in phases) and not engine.errors
            results.append((m.name, success))
            if success:
                provisioned.append(m)
        except Exception as e:
            if console:
                console.error(f"Provisioning failed for {m.name}: {e}")
            results.append((m.name, False))

    # Step 3: Generate workspace file
    if console and not quiet:
        console.step(3, 6, "Generate workspace file")

    if provisioned:
        workspace_content = generate_workspace(provisioned)
        await ssh.run("mkdir -p ~/projects")
        upload_cmd = f"cat > ~/projects/board.code-workspace << 'WSEOF'\n{workspace_content}\nWSEOF"
        await ssh.run(upload_cmd, check=False)
        if console and not quiet:
            console.success("Uploaded board.code-workspace")
    elif console and not quiet:
        console.warn("No projects provisioned successfully, skipping workspace file")

    # Step 4: Generate check script
    if console and not quiet:
        console.step(4, 6, "Generate health check script")

    if provisioned:
        check_content = generate_check_script(provisioned)
        await ssh.run("mkdir -p ~/projects/.board")
        upload_cmd = f"cat > ~/projects/.board/check.sh << 'CHECKEOF'\n{check_content}\nCHECKEOF"
        await ssh.run(upload_cmd, check=False)
        await ssh.run("chmod +x ~/projects/.board/check.sh", check=False)
        if console and not quiet:
            console.success("Uploaded check.sh")

        # Install alias
        await ssh.run(
            "grep -q 'alias check=' ~/.bashrc "
            "|| echo 'alias check=\"bash ~/projects/.board/check.sh\"' >> ~/.bashrc",
            check=False,
        )
        if console and not quiet:
            console.success("Installed 'check' alias in .bashrc")
    elif console and not quiet:
        console.warn("No projects provisioned successfully, skipping check script")

    # Step 5: Copy manifests to VM
    if console and not quiet:
        console.step(5, 6, "Copy manifests to VM")

    await ssh.run("mkdir -p ~/projects/.board/project-manifests", check=False)
    for m in manifests:
        # Upload manifest content
        import io

        from ruamel.yaml import YAML

        yaml = YAML()
        buf = io.StringIO()
        yaml.dump(m.model_dump(by_alias=True, exclude_none=True), buf)
        content = buf.getvalue()
        upload_cmd = (
            f"cat > ~/projects/.board/project-manifests/{m.name}.project.yaml << 'MEOF'\n"
            f"{content}\nMEOF"
        )
        await ssh.run(upload_cmd, check=False)
        if console and not quiet:
            console.success(f"Copied {m.name}.project.yaml")

    # Step 6: Summary
    if console and not quiet:
        console.step(6, 6, "Summary")

    elapsed = time.monotonic() - start_time
    elapsed_min = int(elapsed) // 60
    elapsed_sec = int(elapsed) % 60

    success_count = sum(1 for _, ok in results if ok)
    fail_count = sum(1 for _, ok in results if not ok)

    if console and not quiet:
        lines = []
        for name, ok in results:
            status = "SUCCESS" if ok else "FAILED"
            lines.append(f"{name:<20} {status}")
        lines.append("")
        lines.append(
            f"Total: {len(manifests)} project(s), {success_count} succeeded, {fail_count} failed"
        )
        lines.append(f"Time: {elapsed_min}m {elapsed_sec}s")
        console.summary_box("Provisioning Results", lines)

    return success_count, fail_count
