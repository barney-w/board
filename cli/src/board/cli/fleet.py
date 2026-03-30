"""board fleet — fleet status dashboard with concurrent SSH metrics collection."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import typer

from board.core import config as cfg
from board.core.errors import SSHError
from board.ui import console as con

DEFAULT_LOCATION = "australiaeast"
DEFAULT_REGION = "aue"


async def _collect_metrics(
    dev_name: str,
    hostname: str,
    key_path: str,
) -> dict[str, Any]:
    """SSH into a running VM and collect metrics. Returns a dict of metrics."""
    from board.ssh.session import SSHSession

    metrics: dict[str, Any] = {"dev_name": dev_name, "ttfc": None, "health": None, "issues": []}

    try:
        async with SSHSession() as ssh:
            await ssh.connect(hostname, username="devuser", key_path=key_path)

            # Read metrics JSON and last-check in one SSH call
            result = await ssh.run(
                "cat ~/.board/metrics.json 2>/dev/null; echo '---'; "
                "cat ~/.board/last-check 2>/dev/null",
                check=False,
            )
            raw_output = result.stdout if result else ""
            output = raw_output.decode() if isinstance(raw_output, bytes) else (raw_output or "")

            parts = output.split("---", 1)
            json_part = parts[0] if parts else ""
            check_part = parts[1] if len(parts) > 1 else ""

            # Extract TTFC
            import re

            ttfc_match = re.search(r'"time_to_first_commit_minutes":\s*(\d+)', json_part)
            if ttfc_match:
                metrics["ttfc"] = int(ttfc_match.group(1))

            # Extract health
            passed_match = re.search(r"PASSED=(\d+)", check_part)
            total_match = re.search(r"TOTAL=(\d+)", check_part)
            if passed_match and total_match:
                metrics["health"] = {
                    "passed": int(passed_match.group(1)),
                    "total": int(total_match.group(1)),
                }

            # Extract issues
            issues_match = re.search(r"ISSUES=(.*)", check_part)
            if issues_match and issues_match.group(1) != "none":
                metrics["issues"] = [issues_match.group(1)]

    except (SSHError, Exception):
        pass  # Best effort

    return metrics


async def _run_fleet(env: str, region_short: str) -> None:
    """Collect fleet status and display dashboard."""
    environment = env or os.environ.get("BOARD_ENVIRONMENT", "personal")
    region = region_short or DEFAULT_REGION
    rg = cfg.resource_group(environment, region)

    con.header("Fleet Status")

    from board.azure.auth import get_credential, get_subscription_id
    from board.azure.compute import list_vms

    credential = get_credential()
    sub_id = await get_subscription_id()

    with con.spin("Loading VMs..."):
        vms = await list_vms(credential, sub_id, rg)

    if not vms:
        con.info(f"No boards found in {rg}")
        return

    # Collect metrics from running VMs concurrently
    tasks = []
    for vm in vms:
        dev_name = vm["name"].rsplit("-", 1)[-1] if "-" in vm["name"] else vm["name"]
        if vm["power_state"] == "running":
            fqdn = cfg.hostname(dev_name, DEFAULT_LOCATION)
            key_path = cfg.ssh_key_path_expanded(dev_name)
            if key_path.exists():
                tasks.append(_collect_metrics(dev_name, fqdn, str(key_path)))
            else:

                async def _empty_metrics(dn: str = dev_name) -> dict[str, Any]:
                    return {
                        "dev_name": dn,
                        "ttfc": None,
                        "health": None,
                        "issues": [],
                    }

                tasks.append(_empty_metrics())

    metrics_results = {}
    if tasks:
        with con.spin("Collecting metrics via SSH..."):
            results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, dict):
                metrics_results[r["dev_name"]] = r

    # Display table
    from rich.table import Table

    total = len(vms)
    active = sum(1 for vm in vms if vm["power_state"] == "running")

    table = Table(title=f"Boards  {active} active / {total} total")
    table.add_column("", width=2)
    table.add_column("Name", style="bold", min_width=14)
    table.add_column("Status", min_width=14)
    table.add_column("Size", min_width=12)
    table.add_column("TTFC", min_width=8)
    table.add_column("Health", min_width=8)

    ttfc_sum = 0
    ttfc_count = 0
    health_total = 0
    health_passed = 0
    all_issues: list[str] = []

    for vm in vms:
        dev_name = vm["name"].rsplit("-", 1)[-1] if "-" in vm["name"] else vm["name"]
        state = vm["power_state"]

        if state == "running":
            dot = "[green]●[/green]"
        elif "deallocat" in state:
            dot = "[dim]○[/dim]"
        else:
            dot = "[yellow]◉[/yellow]"

        # Get metrics for this VM
        m = metrics_results.get(dev_name, {})
        ttfc_str = "--"
        health_str = "--"

        if m.get("ttfc") is not None:
            ttfc_str = f"{m['ttfc']}m"
            ttfc_sum += m["ttfc"]
            ttfc_count += 1

        if m.get("health"):
            h = m["health"]
            health_str = f"{h['passed']}/{h['total']}"
            health_total += h["total"]
            health_passed += h["passed"]

        if m.get("issues"):
            for issue in m["issues"]:
                all_issues.append(f"{dev_name}: {issue}")

        table.add_row(dot, dev_name, state, vm.get("vm_size") or "?", ttfc_str, health_str)

    con.console.print(table)
    con.console.print()

    # Aggregates
    if ttfc_count > 0:
        avg_ttfc = ttfc_sum // ttfc_count
        con.info(f"Avg TTFC     {avg_ttfc} minutes (across {ttfc_count} boards)")

    if health_total > 0:
        health_pct = health_passed * 100 // health_total
        con.info(f"Health       {health_passed}/{health_total} checks passing ({health_pct}%)")

    if all_issues:
        con.console.print()
        con.console.print("  [bold]Common Issues[/bold]")
        for issue in all_issues:
            con.console.print(f"    [red]![/red] {issue}")

    con.console.print()


def fleet_command(
    env: str = typer.Option("", "--env", help="Environment name."),
    region_short: str = typer.Option("", "--region-short", help="Short region code (e.g. aue)."),
) -> None:
    """Show fleet dashboard with status and metrics for all boards."""
    asyncio.run(_run_fleet(env, region_short))
