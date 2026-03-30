"""Naming conventions, env var resolution, bicepparam discovery.

Naming derivations MUST produce identical strings to extension/src/config.ts.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Developer name validation: 1-12 chars, lowercase, starts with letter
DEV_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]{0,11}$")


def validate_developer_name(name: str) -> bool:
    """Check if a developer name is valid."""
    return bool(DEV_NAME_PATTERN.match(name))


# ── Naming convention functions (must match extension/src/config.ts) ──


def ssh_host_alias(name: str) -> str:
    """devvm-{name}"""
    return f"devvm-{name}"


def hostname(name: str, region: str) -> str:
    """devvm-{name}.{region}.cloudapp.azure.com"""
    return f"devvm-{name}.{region}.cloudapp.azure.com"


def resource_group(environment: str, region_short: str) -> str:
    """rg-{env}-{regionShort}-devvm"""
    return f"rg-{environment}-{region_short}-devvm"


def vm_name(environment: str, region_short: str, name: str) -> str:
    """vm-{env}-{regionShort}-devvm-{name}"""
    return f"vm-{environment}-{region_short}-devvm-{name}"


def ssh_key_path(name: str) -> str:
    """~/.ssh/devvm-{name}"""
    return f"~/.ssh/devvm-{name}"


def ssh_key_path_expanded(name: str) -> Path:
    """Fully expanded SSH key path."""
    return Path.home() / ".ssh" / f"devvm-{name}"


def tunnel_url(name: str, explicit_url: str = "") -> str:
    """Get tunnel URL, deriving from name if not explicitly set."""
    if explicit_url:
        return explicit_url
    if name:
        return f"https://vscode.dev/tunnel/devvm-{name}"
    return ""


# ── Env var resolution ──


def get_env(key: str, default: str = "") -> str:
    """Get an environment variable with BOARD_ prefix fallback."""
    return os.environ.get(key, os.environ.get(f"BOARD_{key}", default))


def is_non_interactive() -> bool:
    """Check if running in non-interactive mode."""
    return os.environ.get("BOARD_NON_INTERACTIVE", "").lower() in ("1", "true", "yes")


def is_dry_run() -> bool:
    """Check if running in dry-run mode."""
    return os.environ.get("BOARD_DRY_RUN", "").lower() in ("1", "true", "yes")


# ── Bicepparam discovery ──


def discover_bicepparams(infra_dir: Path | None = None) -> list[tuple[str, Path]]:
    """Find all .bicepparam files and extract environment names.

    Returns list of (environment_name, file_path) tuples.
    Looks in infra/config/*.bicepparam relative to the project root.
    """
    if infra_dir is None:
        infra_dir = _find_infra_dir()
    config_dir = infra_dir / "config"
    if not config_dir.is_dir():
        return []
    params = []
    for p in sorted(config_dir.glob("*.bicepparam")):
        env_name = p.stem
        if env_name == "example":
            continue
        params.append((env_name, p))
    return params


def _find_infra_dir() -> Path:
    """Locate the infra/ directory by walking up from cwd."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "infra"
        if candidate.is_dir():
            return candidate
    return cwd / "infra"
