"""Policy loading and enforcement.

Policies are loaded from board.policies.yaml at the project root.
Enforcement runs before provisioning to reject disallowed configurations.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ruamel.yaml import YAML

from board.core.errors import PolicyViolationError
from board.models.policies import PoliciesConfig


def find_policies_file() -> Path | None:
    """Locate board.policies.yaml by walking up from cwd."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "board.policies.yaml"
        if candidate.is_file():
            return candidate
    return None


def load(path: Path | None = None) -> PoliciesConfig | None:
    """Load policies from YAML file. Returns None if no file found."""
    if path is None:
        path = find_policies_file()
    if path is None or not path.is_file():
        return None
    yaml = YAML()
    data = yaml.load(path)
    if data is None:
        return PoliciesConfig()
    return PoliciesConfig(**data)


def enforce(
    policies: PoliciesConfig,
    *,
    vm_sku: str,
    region: str,
    auth_method: str,
    developer_name: str,
    resource_group: str,
) -> list[str]:
    """Check deployment params against policies. Returns list of violations.

    Raises PolicyViolationError if any hard violations found.
    Returns warnings for soft issues.
    """
    violations: list[str] = []
    warnings: list[str] = []

    # VM size
    if policies.allowed_vm_sizes and vm_sku not in policies.allowed_vm_sizes:
        allowed = ", ".join(policies.allowed_vm_sizes)
        violations.append(f"VM size '{vm_sku}' not in allowed sizes: {allowed}")

    # Region
    if policies.allowed_regions and region not in policies.allowed_regions:
        allowed = ", ".join(policies.allowed_regions)
        violations.append(f"Region '{region}' not in allowed regions: {allowed}")

    # Auth method
    if policies.require_entra_auth and auth_method != "entra-id":
        violations.append("Policy requires Entra ID authentication (SSH key not allowed)")

    # VM count per user
    existing_count = _count_user_vms(developer_name, resource_group)
    if existing_count >= policies.max_vms_per_user:
        violations.append(
            f"User '{developer_name}' already has {existing_count} VM(s) "
            f"(max: {policies.max_vms_per_user})"
        )

    # Total VM count
    total_count = _count_total_vms(resource_group)
    if total_count >= policies.max_vms_total:
        violations.append(f"Resource group has {total_count} VM(s) (max: {policies.max_vms_total})")

    if violations:
        msg = "Policy violations:\n" + "\n".join(f"  - {v}" for v in violations)
        raise PolicyViolationError(msg)

    return warnings


def _count_user_vms(developer_name: str, resource_group: str) -> int:
    """Count existing VMs owned by a developer via Azure tags."""
    result = subprocess.run(
        [
            "az",
            "vm",
            "list",
            "-g",
            resource_group,
            "--query",
            f"[?tags.project=='devvm' && tags.owner=='{developer_name}'] | length(@)",
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def _count_total_vms(resource_group: str) -> int:
    """Count total devvm-tagged VMs in the resource group."""
    result = subprocess.run(
        [
            "az",
            "vm",
            "list",
            "-g",
            resource_group,
            "--query",
            "[?tags.project=='devvm'] | length(@)",
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0
