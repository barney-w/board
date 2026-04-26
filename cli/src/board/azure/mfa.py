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

# Security group used to scope the MFA policy.
BOARD_GROUP_NAME = "Board VM Users"
_GROUPS_URL = "https://graph.microsoft.com/v1.0/groups"


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


async def find_board_group() -> str | None:
    """Find the 'Board VM Users' security group, return its object ID or ``None``."""
    try:
        raw = await az_text(
            "rest",
            "--method",
            "GET",
            "--url",
            f"{_GROUPS_URL}?$filter=displayName eq '{BOARD_GROUP_NAME}'",
            timeout=15,
        )
        data = json.loads(raw)
    except (BoardError, json.JSONDecodeError):
        return None

    for group in data.get("value", []):
        if group.get("displayName") == BOARD_GROUP_NAME:
            return group.get("id")  # type: ignore[no-any-return]
    return None


async def ensure_board_group() -> tuple[str | None, str]:
    """Find or create the 'Board VM Users' security group.

    Returns ``(group_object_id, message)``.  ``group_object_id`` is
    ``None`` when creation fails (e.g. insufficient permissions).
    """
    existing = await find_board_group()
    if existing:
        return existing, f"Using existing group: {BOARD_GROUP_NAME}"

    body = {
        "displayName": BOARD_GROUP_NAME,
        "description": "Users subject to Board MFA policy for Azure Linux VM SSH.",
        "mailEnabled": False,
        "mailNickname": "BoardVMUsers",
        "securityEnabled": True,
    }
    try:
        raw = await az_text(
            "rest",
            "--method",
            "POST",
            "--url",
            _GROUPS_URL,
            "--body",
            json.dumps(body),
            "--headers",
            "Content-Type=application/json",
            timeout=15,
        )
        data = json.loads(raw)
        group_id = data.get("id")
        if group_id:
            return group_id, f"Created security group: {BOARD_GROUP_NAME}"
        return None, "Group creation returned no ID"
    except BoardError as exc:
        return None, f"Could not create security group: {exc}"


async def get_signed_in_user_id() -> str | None:
    """Return the object ID of the currently signed-in Entra ID user."""
    try:
        raw = await az_text(
            "rest",
            "--method",
            "GET",
            "--url",
            "https://graph.microsoft.com/v1.0/me?$select=id",
            timeout=15,
        )
        data = json.loads(raw)
        return data.get("id")  # type: ignore[no-any-return]
    except (BoardError, json.JSONDecodeError):
        return None


async def add_member_to_board_group(group_id: str, user_object_id: str) -> tuple[bool, str]:
    """Add a user to the Board VM Users security group.

    Returns ``(success, message)``.  Silently succeeds if the user is
    already a member (Graph API returns 400 with "already exist").
    """
    body = {
        "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_object_id}",
    }
    try:
        await az_text(
            "rest",
            "--method",
            "POST",
            "--url",
            f"{_GROUPS_URL}/{group_id}/members/$ref",
            "--body",
            json.dumps(body),
            "--headers",
            "Content-Type=application/json",
            timeout=15,
        )
        return True, "User added to group"
    except BoardError as exc:
        detail = str(exc)
        # Graph returns 400 when the member already exists.
        if "already exist" in detail.lower() or "already a member" in detail.lower():
            return True, "User is already a member of the group"
        return False, f"Could not add user to group: {detail}"


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


async def check_mfa_policy() -> tuple[bool, str | None]:
    """Check whether a Conditional Access MFA policy exists for VM SSH.

    Returns ``(exists, policy_display_name | None)``.  Read-only — does
    not attempt to create a policy and requires no elevated role.
    """
    existing = await find_existing_policy()
    if existing:
        name = existing.get("displayName")
        return True, str(name) if name else "unknown"
    return False, None


async def create_mfa_policy(group_id: str) -> tuple[bool, str]:
    """Create a Conditional Access policy requiring MFA for VM SSH.

    The policy is scoped to *group_id* (an Entra ID security group
    object-ID) so that only members of that group are affected.

    Returns ``(success, message)`` — never raises.  Requires the
    signed-in user to hold **Conditional Access Administrator** or
    **Global Administrator** in Entra ID.
    """
    # Pre-check: skip if already present.
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
            "users": {"includeGroups": [group_id]},
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
        if "not licensed" in detail.lower() or "upgrade your subscription" in detail.lower():
            return False, (
                "Conditional Access requires an Entra ID P1 or P2 licence. "
                "Your tenant does not have this feature enabled."
            )
        if "Forbidden" in detail or "403" in detail or "Authorization" in detail:
            return False, (
                "Insufficient permissions to create Conditional Access policy. "
                "Requires Conditional Access Administrator or Global Administrator role."
            )
        return False, f"Could not create MFA policy: {detail}"
