"""board policies — view and validate policy configuration."""

from __future__ import annotations

import typer

from board.core import policies as pol
from board.ui import console as con


def show_command() -> None:
    """Show current policy configuration."""
    policies = pol.load()
    if policies is None:
        con.warn("No board.policies.yaml found")
        raise typer.Exit(1)

    path = pol.find_policies_file()
    con.header("Board Policies")
    con.info(f"File: {path}")
    con.info("")

    lines = [
        f"Max VMs per user:  {policies.max_vms_per_user}",
        f"Max VMs total:     {policies.max_vms_total}",
        f"Allowed VM sizes:  {', '.join(policies.allowed_vm_sizes)}",
        f"Allowed regions:   {', '.join(policies.allowed_regions)}",
        f"Require Entra ID:  {policies.require_entra_auth}",
        f"Require MFA:       {policies.require_mfa}",
        "",
        "Schedules:",
        f"  Auto-shutdown:   {'enabled' if policies.auto_shutdown.enabled else 'disabled'}"
        + (f" at {policies.auto_shutdown.time}" if policies.auto_shutdown.enabled else ""),
        f"  Auto-start:      {'enabled' if policies.auto_start.enabled else 'disabled'}"
        + (f" at {policies.auto_start.time}" if policies.auto_start.enabled else ""),
        "",
        "Expiration:",
        f"  Enabled:         {policies.expiration.enabled}",
    ]
    if policies.expiration.enabled:
        lines.append(f"  Max days:        {policies.expiration.max_days}")

    con.summary_box("Active Policies", lines)
