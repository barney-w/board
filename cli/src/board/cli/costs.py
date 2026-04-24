"""board costs — per-developer cost tracking via Azure Cost Management."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import typer

from board.core import config as cfg
from board.core.errors import BoardError
from board.ui import console as con

DEFAULT_REGION = "aue"


def costs_command(
    developer: str = typer.Option("", "--developer", "-d", help="Filter by developer name."),
    env: str = typer.Option("", "--env", help="Environment name."),
    month: str = typer.Option("", "--month", "-m", help="Month in YYYY-MM format (default: current)."),
) -> None:
    """Show cost breakdown for developer VMs."""

    async def _run() -> None:
        from board.azure.auth import get_subscription_id
        from board.azure.costs import query_costs

        resolved_env = env or "personal"
        rg = cfg.resource_group(resolved_env, DEFAULT_REGION)

        try:
            sub_id = await get_subscription_id()
        except RuntimeError as exc:
            con.error(str(exc))
            raise typer.Exit(1) from exc

        # Resolve date range
        now = datetime.now(tz=UTC)
        if month:
            from_date = f"{month}-01"
            # First day of next month
            year, mon = int(month[:4]), int(month[5:7])
            to_date = f"{year + 1}-01-01" if mon == 12 else f"{year}-{mon + 1:02d}-01"
        else:
            from_date = now.strftime("%Y-%m-01")
            to_date = now.strftime("%Y-%m-%d")

        con.header("Developer VM Costs")
        con.info(f"Resource group: {rg}")
        con.info(f"Period: {from_date} to {to_date}")

        try:
            with con.spin("Querying Cost Management API..."):
                results = await query_costs(
                    sub_id,
                    rg,
                    from_date=from_date,
                    to_date=to_date,
                )
        except BoardError as exc:
            con.error(str(exc))
            raise typer.Exit(1) from exc

        if not results:
            con.info("No cost data found for this period.")
            return

        # Filter by developer if specified
        if developer:
            results = [r for r in results if r["owner"] == developer]
            if not results:
                con.info(f"No costs found for developer: {developer}")
                return

        # Display
        from rich.table import Table

        table = Table(title="Cost by Developer")
        table.add_column("Developer", style="bold")
        table.add_column("Cost", justify="right")
        table.add_column("Currency")

        total = 0.0
        for row in results:
            cost = row["cost"]
            total += cost
            table.add_row(
                row["owner"],
                f"${cost:.2f}",
                row["currency"],
            )

        table.add_section()
        currency = results[0]["currency"] if results else "AUD"
        table.add_row("[bold]Total[/bold]", f"[bold]${total:.2f}[/bold]", currency)

        con.console.print(table)

    asyncio.run(_run())
