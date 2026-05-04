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


def rg_suffix(resource_group_name: str) -> str:
    """Strip leading 'rg-' from a resource group name to use as a naming prefix.

    rg-platform-prod -> platform-prod
    my-team -> my-team
    """
    return resource_group_name.removeprefix("rg-")


def vm_name(resource_group_name: str, name: str) -> str:
    """vm-{rg-suffix}-{name}"""
    return f"vm-{rg_suffix(resource_group_name)}-{name}"


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


# ── Bicepparam preset loading ──

# Keys that the wizard recognises in a preset file. Anything else is ignored.
_PRESET_KEYS = {
    "resourceGroup",
    "location",
    "vmSku",
    "allowedSshSourceIP",
    "enableAutoStart",
    "autoStartTime",
}


def load_preset(path: Path) -> dict[str, str]:
    """Parse a bicepparam preset file and return a dict of recognised values.

    Only handles ``param key = 'value'`` lines (plus bool literals). Anything
    more complex (objects, references) is ignored — presets are meant for
    simple defaults the wizard can pre-fill.
    """
    if not path.is_file():
        msg = f"Preset file not found: {path}"
        raise FileNotFoundError(msg)
    out: dict[str, str] = {}
    pat = re.compile(r"^\s*param\s+(\w+)\s*=\s*(.+?)\s*(?://.*)?$")
    for line in path.read_text().splitlines():
        m = pat.match(line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if key not in _PRESET_KEYS:
            continue
        if raw.startswith(("'", '"')) and raw.endswith(("'", '"')):
            out[key] = raw[1:-1]
        elif raw in ("true", "false"):
            out[key] = raw
        # else: skip — not a simple literal
    return out


def _find_infra_dir() -> Path:
    """Locate the infra/ directory by walking up from cwd."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "infra"
        if candidate.is_dir():
            return candidate
    return cwd / "infra"
