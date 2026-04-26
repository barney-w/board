"""Conditional Access MFA policy for Azure Linux VM SSH login.

Creates a Conditional Access policy in Entra ID that requires MFA for
the "Microsoft Azure Linux Virtual Machine Sign-In" application. This
ensures that ``az ssh vm`` / ``az ssh proxy`` connections always trigger
an MFA challenge.

Requires the signed-in user to hold Conditional Access Administrator
(or Global Administrator) role in the tenant.
"""

from __future__ import annotations

import json

from board.azure.az import az_json, az_text
from board.core.errors import BoardError

# Display name for the Conditional Access policy we manage.
_POLICY_DISPLAY_NAME = "Board: Require MFA for Azure Linux VM SSH"

# Graph API endpoint for Conditional Access policies.
_CA_POLICIES_URL = "https://graph.microsoft.com/v1.0/identity/conditionalAccess/policies"


async def _resolve_vm_signin_app_id() -> str:
    """Look up the Azure Linux VM Sign-In service principal in the tenant.

    Returns the appId used in Conditional Access policy conditions.
    Falls back to the well-known first-party app ID if the lookup fails.
    """
    # Well-known first-party app ID registered by Microsoft for
    # "Microsoft Azure Linux Virtual Machine Sign-In".
    fallback = "ce6ff14a-7c3c-45a7-86db-e7ea24e2022d"

    try:
        result = await az_json(
            "ad",
            "sp",
            "list",
            "--display-name",
            "Microsoft Azure Linux Virtual Machine Sign-In",
            "--query",
            "[0].appId",
            "-o",
            "json",
            timeout=15,
        )
        if result and isinstance(result, str):
            return result
    except BoardError:
        pass

    return fallback


async def find_existing_policy() -> dict[str, object] | None:
    """Return the existing Board MFA policy if one exists, else None.

    Checks both by display-name match and by whether any enabled policy
    targets the VM Sign-In app with an MFA grant control.
    """
    try:
        raw = await az_text("rest", "--method", "GET", "--url", _CA_POLICIES_URL, timeout=30)
        data = json.loads(raw)
    except (BoardError, json.JSONDecodeError):
        return None

    app_id = await _resolve_vm_signin_app_id()

    for policy in data.get("value", []):
        # Exact name match — this is our policy.
        if policy.get("displayName") == _POLICY_DISPLAY_NAME:
            return policy  # type: ignore[no-any-return]

        # Also detect any other policy that already enforces MFA for VM SSH.
        apps = policy.get("conditions", {}).get("applications", {}).get("includeApplications", [])
        grants = policy.get("grantControls", {}).get("builtInControls", [])
        if app_id in apps and "mfa" in grants:
            return policy  # type: ignore[no-any-return]

    return None


async def ensure_mfa_policy() -> tuple[bool, str]:
    """Ensure a Conditional Access policy requiring MFA for VM SSH exists.

    Returns ``(success, message)`` — never raises.  If the signed-in user
    lacks Conditional Access Administrator permissions the call will fail
    gracefully with a descriptive message.
    """
    existing = await find_existing_policy()
    if existing:
        name = existing.get("displayName", "unknown")
        state = existing.get("state", "unknown")
        return True, f"MFA policy already exists: {name} ({state})"

    app_id = await _resolve_vm_signin_app_id()

    policy_body = {
        "displayName": _POLICY_DISPLAY_NAME,
        "state": "enabled",
        "conditions": {
            "applications": {"includeApplications": [app_id]},
            "users": {"includeUsers": ["All"]},
        },
        "grantControls": {
            "operator": "OR",
            "builtInControls": ["mfa"],
        },
    }

    try:
        await az_text(
            "rest",
            "--method",
            "POST",
            "--url",
            _CA_POLICIES_URL,
            "--body",
            json.dumps(policy_body),
            "--headers",
            "Content-Type=application/json",
            timeout=30,
        )
        return True, "MFA policy created for Azure Linux VM SSH"
    except BoardError as exc:
        detail = str(exc)
        if "Forbidden" in detail or "403" in detail or "Authorization" in detail:
            return False, (
                "Insufficient permissions to create Conditional Access policy. "
                "Requires Conditional Access Administrator or Global Administrator role."
            )
        return False, f"Could not create MFA policy: {detail}"
