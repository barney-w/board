"""Azure authentication — credential and subscription resolution."""

from __future__ import annotations

import os
from typing import Any

from azure.identity import DefaultAzureCredential

from board.azure.az import az_json, az_text


def get_credential() -> DefaultAzureCredential:
    """Get Azure credential, excluding problematic providers.

    Excludes SharedTokenCacheCredential and PowerShellCredential which
    can cause hangs or confusing auth failures on developer machines.
    """
    return DefaultAzureCredential(
        exclude_shared_token_cache_credential=True,
        exclude_powershell_credential=True,
    )


async def get_subscription_id() -> str:
    """Get current subscription ID from environment or az CLI.

    Checks AZURE_SUBSCRIPTION_ID and BOARD_SUBSCRIPTION_ID env vars
    first, then falls back to ``az account show``.

    Raises:
        RuntimeError: If no subscription could be determined.
    """
    for key in ("AZURE_SUBSCRIPTION_ID", "BOARD_SUBSCRIPTION_ID"):
        value = os.environ.get(key, "")
        if value:
            return value

    sub_id = await az_text("account", "show", "--query", "id", "-o", "tsv", timeout=30)
    if not sub_id:
        msg = "No Azure subscription found. Set AZURE_SUBSCRIPTION_ID or run 'az login'."
        raise RuntimeError(msg)
    return sub_id


async def get_tenant_id() -> str:
    """Return the current Azure tenant ID.

    Raises:
        BoardError: If the az CLI call fails.
    """
    return await az_text("account", "show", "--query", "tenantId", "-o", "tsv", timeout=30)


async def list_subscriptions() -> list[dict[str, Any]]:
    """List available Azure subscriptions.

    Returns a list of dicts with keys: name, id, is_default.
    """
    raw = await az_json(
        "account", "list", "--query", "[].[name, id, isDefault]", "-o", "json", timeout=30
    )
    return [{"name": entry[0], "id": entry[1], "is_default": entry[2]} for entry in raw]
