"""Azure Cost Management API queries for devvm cost tracking."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from board.azure.az import az_text
from board.core.errors import BoardError


async def query_costs(
    subscription_id: str,
    resource_group: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict[str, Any]]:
    """Query costs for devvm-tagged resources, grouped by owner tag.

    Returns list of dicts: [{"owner": "jbloggs", "cost": 42.50, "currency": "AUD"}, ...]

    Uses the Cost Management Query API via ``az rest``.
    """
    now = datetime.now(tz=UTC)
    if to_date is None:
        to_date = now.strftime("%Y-%m-%d")
    if from_date is None:
        # First day of current month
        from_date = now.strftime("%Y-%m-01")

    scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
    url = f"{scope}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"

    body = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {"from": from_date, "to": to_date},
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [{"type": "TagKey", "name": "owner"}],
            "filter": {
                "tags": {"name": "project", "operator": "In", "values": ["devvm"]},
            },
        },
    }

    raw = await az_text(
        "rest",
        "--method",
        "POST",
        "--url",
        url,
        "--body",
        json.dumps(body),
        timeout=60,
    )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BoardError(f"Cost Management returned invalid JSON: {exc}") from exc

    rows = data.get("properties", {}).get("rows", [])
    columns = data.get("properties", {}).get("columns", [])

    if not rows or not columns:
        return []

    # Map column names to indices
    col_map = {col["name"]: i for i, col in enumerate(columns)}
    cost_idx = col_map.get("Cost", 0)
    owner_idx = col_map.get("TagValue", 1)
    currency_idx = col_map.get("Currency", 2)

    results = []
    for row in rows:
        if len(row) <= max(cost_idx, owner_idx):
            continue  # skip malformed rows
        results.append(
            {
                "owner": row[owner_idx] or "untagged",
                "cost": round(float(row[cost_idx]), 2),
                "currency": row[currency_idx] if currency_idx < len(row) else "AUD",
            }
        )

    return sorted(results, key=lambda r: r["cost"], reverse=True)
