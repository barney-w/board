"""Tests for board.azure.mfa — Conditional Access MFA policy management."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from board.azure.mfa import (
    _POLICY_DISPLAY_NAME,
    DEFAULT_GROUP_NAME,
    _resolve_vm_signin_app_id,
    add_member_to_board_group,
    check_mfa_policy,
    create_mfa_policy,
    ensure_board_group,
    find_board_group,
    find_existing_policy,
    get_signed_in_user_id,
)
from board.core.errors import BoardError


class TestResolveVmSigninAppId:
    """Service principal lookup."""

    @pytest.fixture(autouse=True)
    def _patch_az(self) -> None:
        self._az_json = AsyncMock()
        self._patcher = patch("board.azure.mfa.az_json", self._az_json)
        self._patcher.start()
        yield  # type: ignore[misc]
        self._patcher.stop()

    async def test_returns_app_id_from_lookup(self) -> None:
        self._az_json.return_value = "abc-123"
        result = await _resolve_vm_signin_app_id()
        assert result == "abc-123"

    async def test_falls_back_on_error(self) -> None:
        self._az_json.side_effect = BoardError("not found")
        result = await _resolve_vm_signin_app_id()
        # Should return the well-known fallback ID.
        assert result == "ce6ff14a-7c3c-45a7-86db-e7ea24e2022d"

    async def test_falls_back_on_empty_result(self) -> None:
        self._az_json.return_value = None
        result = await _resolve_vm_signin_app_id()
        assert result == "ce6ff14a-7c3c-45a7-86db-e7ea24e2022d"


class TestFindExistingPolicy:
    """Policy lookup via Graph API."""

    @pytest.fixture(autouse=True)
    def _patch_az(self) -> None:
        self._az_text = AsyncMock()
        self._resolve = AsyncMock(return_value="ce6ff14a-7c3c-45a7-86db-e7ea24e2022d")
        self._text_patcher = patch("board.azure.mfa.az_text", self._az_text)
        self._resolve_patcher = patch("board.azure.mfa._resolve_vm_signin_app_id", self._resolve)
        self._text_patcher.start()
        self._resolve_patcher.start()
        yield  # type: ignore[misc]
        self._text_patcher.stop()
        self._resolve_patcher.stop()

    async def test_finds_policy_by_name(self) -> None:
        policy = {"displayName": _POLICY_DISPLAY_NAME, "state": "enabled"}
        self._az_text.return_value = json.dumps({"value": [policy]})
        result = await find_existing_policy()
        assert result is not None
        assert result["displayName"] == _POLICY_DISPLAY_NAME

    async def test_finds_policy_by_app_and_mfa(self) -> None:
        policy = {
            "displayName": "Some other name",
            "state": "enabled",
            "conditions": {
                "applications": {"includeApplications": ["ce6ff14a-7c3c-45a7-86db-e7ea24e2022d"]}
            },
            "grantControls": {"builtInControls": ["mfa"]},
        }
        self._az_text.return_value = json.dumps({"value": [policy]})
        result = await find_existing_policy()
        assert result is not None

    async def test_returns_none_when_no_match(self) -> None:
        policy = {"displayName": "Unrelated policy", "state": "enabled"}
        self._az_text.return_value = json.dumps({"value": [policy]})
        result = await find_existing_policy()
        assert result is None

    async def test_returns_none_on_api_error(self) -> None:
        self._az_text.side_effect = BoardError("403 Forbidden")
        result = await find_existing_policy()
        assert result is None


class TestCheckMfaPolicy:
    """Read-only policy check."""

    @pytest.fixture(autouse=True)
    def _patch(self) -> None:
        self._find = AsyncMock(return_value=None)
        self._patcher = patch("board.azure.mfa.find_existing_policy", self._find)
        self._patcher.start()
        yield  # type: ignore[misc]
        self._patcher.stop()

    async def test_returns_true_when_exists(self) -> None:
        self._find.return_value = {
            "displayName": _POLICY_DISPLAY_NAME,
            "state": "enabled",
        }
        exists, name = await check_mfa_policy()
        assert exists is True
        assert name == _POLICY_DISPLAY_NAME

    async def test_returns_false_when_missing(self) -> None:
        self._find.return_value = None
        exists, name = await check_mfa_policy()
        assert exists is False
        assert name is None


class TestFindBoardGroup:
    """Security group lookup."""

    @pytest.fixture(autouse=True)
    def _patch_az(self) -> None:
        self._az_text = AsyncMock()
        self._patcher = patch("board.azure.mfa.az_text", self._az_text)
        self._patcher.start()
        yield  # type: ignore[misc]
        self._patcher.stop()

    async def test_returns_group_id_when_found(self) -> None:
        group = {"displayName": DEFAULT_GROUP_NAME, "id": "group-abc-123"}
        self._az_text.return_value = json.dumps({"value": [group]})
        result = await find_board_group()
        assert result == "group-abc-123"

    async def test_finds_custom_group_name(self) -> None:
        group = {"displayName": "My Custom Group", "id": "custom-group-id"}
        self._az_text.return_value = json.dumps({"value": [group]})
        result = await find_board_group("My Custom Group")
        assert result == "custom-group-id"

    async def test_returns_none_when_not_found(self) -> None:
        self._az_text.return_value = json.dumps({"value": []})
        result = await find_board_group()
        assert result is None

    async def test_returns_none_on_api_error(self) -> None:
        self._az_text.side_effect = BoardError("403 Forbidden")
        result = await find_board_group()
        assert result is None


class TestEnsureBoardGroup:
    """Security group find-or-create."""

    @pytest.fixture(autouse=True)
    def _patch(self) -> None:
        self._find = AsyncMock(return_value=None)
        self._az_text = AsyncMock(return_value="{}")
        patchers = [
            patch("board.azure.mfa.find_board_group", self._find),
            patch("board.azure.mfa.az_text", self._az_text),
        ]
        for p in patchers:
            p.start()
        self._patchers = patchers
        yield  # type: ignore[misc]
        for p in patchers:
            p.stop()

    async def test_returns_existing_group(self) -> None:
        self._find.return_value = "existing-group-id"
        group_id, msg = await ensure_board_group()
        assert group_id == "existing-group-id"
        assert "existing" in msg.lower()
        self._az_text.assert_not_called()

    async def test_creates_group_when_missing(self) -> None:
        self._az_text.return_value = json.dumps({"id": "new-group-id"})
        group_id, msg = await ensure_board_group()
        assert group_id == "new-group-id"
        assert "created" in msg.lower()

    async def test_returns_none_on_creation_failure(self) -> None:
        self._az_text.side_effect = BoardError("403 Forbidden")
        group_id, msg = await ensure_board_group()
        assert group_id is None
        assert "could not create" in msg.lower()

    async def test_passes_custom_group_name(self) -> None:
        self._az_text.return_value = json.dumps({"id": "custom-id"})
        group_id, msg = await ensure_board_group("Corp VM Team")
        assert group_id == "custom-id"
        assert "Corp VM Team" in msg
        # Verify the POST body uses the custom name.
        call_args = self._az_text.call_args
        args = call_args[0]
        body_idx = args.index("--body") + 1
        body = json.loads(args[body_idx])
        assert body["displayName"] == "Corp VM Team"
        assert body["mailNickname"] == "CorpVMTeam"


class TestCreateMfaPolicy:
    """Policy creation (requires elevated role)."""

    _test_group_id = "test-group-object-id"

    @pytest.fixture(autouse=True)
    def _patch(self) -> None:
        self._find = AsyncMock(return_value=None)
        self._resolve = AsyncMock(return_value="ce6ff14a-7c3c-45a7-86db-e7ea24e2022d")
        self._az_text = AsyncMock(return_value="{}")
        patchers = [
            patch("board.azure.mfa.find_existing_policy", self._find),
            patch("board.azure.mfa._resolve_vm_signin_app_id", self._resolve),
            patch("board.azure.mfa.az_text", self._az_text),
        ]
        for p in patchers:
            p.start()
        self._patchers = patchers
        yield  # type: ignore[misc]
        for p in patchers:
            p.stop()

    async def test_creates_policy_scoped_to_group(self) -> None:
        ok, msg = await create_mfa_policy(self._test_group_id)
        assert ok is True
        assert "created" in msg.lower()
        # Verify the POST was made with correct body.
        call_args = self._az_text.call_args
        assert call_args is not None
        args = call_args[0]
        body_idx = args.index("--body") + 1
        body = json.loads(args[body_idx])
        assert body["displayName"] == _POLICY_DISPLAY_NAME
        assert body["state"] == "enabled"
        assert "mfa" in body["grantControls"]["builtInControls"]
        # Must target the group, NOT all users.
        assert body["conditions"]["users"]["includeGroups"] == [self._test_group_id]
        assert "includeUsers" not in body["conditions"]["users"]

    async def test_skips_when_policy_exists(self) -> None:
        self._find.return_value = {
            "displayName": _POLICY_DISPLAY_NAME,
            "state": "enabled",
        }
        ok, msg = await create_mfa_policy(self._test_group_id)
        assert ok is True
        assert "already exists" in msg.lower()
        self._az_text.assert_not_called()

    async def test_handles_licensing_error(self) -> None:
        self._az_text.side_effect = BoardError(
            "Forbidden: Your tenant is not licensed for this feature. "
            "Please upgrade your subscription to access it."
        )
        ok, msg = await create_mfa_policy(self._test_group_id)
        assert ok is False
        assert "licence" in msg.lower() or "P1" in msg

    async def test_handles_permission_error(self) -> None:
        self._az_text.side_effect = BoardError("az rest failed: 403 Forbidden")
        ok, msg = await create_mfa_policy(self._test_group_id)
        assert ok is False
        assert "Conditional Access Administrator" in msg

    async def test_handles_generic_error(self) -> None:
        self._az_text.side_effect = BoardError("az rest failed: network timeout")
        ok, msg = await create_mfa_policy(self._test_group_id)
        assert ok is False
        assert "network timeout" in msg.lower()


class TestGetSignedInUserId:
    """Current user identity lookup."""

    @pytest.fixture(autouse=True)
    def _patch_az(self) -> None:
        self._az_text = AsyncMock()
        self._patcher = patch("board.azure.mfa.az_text", self._az_text)
        self._patcher.start()
        yield  # type: ignore[misc]
        self._patcher.stop()

    async def test_returns_user_id(self) -> None:
        self._az_text.return_value = json.dumps({"id": "user-object-id-123"})
        result = await get_signed_in_user_id()
        assert result == "user-object-id-123"

    async def test_returns_none_on_error(self) -> None:
        self._az_text.side_effect = BoardError("not authenticated")
        result = await get_signed_in_user_id()
        assert result is None


class TestAddMemberToBoardGroup:
    """Group membership management."""

    @pytest.fixture(autouse=True)
    def _patch_az(self) -> None:
        self._az_text = AsyncMock(return_value="")
        self._patcher = patch("board.azure.mfa.az_text", self._az_text)
        self._patcher.start()
        yield  # type: ignore[misc]
        self._patcher.stop()

    async def test_adds_member_successfully(self) -> None:
        ok, msg = await add_member_to_board_group("group-1", "user-1")
        assert ok is True
        assert "added" in msg.lower()
        # Verify the POST body references the user.
        call_args = self._az_text.call_args
        args = call_args[0]
        body_idx = args.index("--body") + 1
        body = json.loads(args[body_idx])
        assert "user-1" in body["@odata.id"]

    async def test_succeeds_when_already_a_member(self) -> None:
        self._az_text.side_effect = BoardError("One or more added object references already exist")
        ok, msg = await add_member_to_board_group("group-1", "user-1")
        assert ok is True
        assert "already" in msg.lower()

    async def test_returns_failure_on_error(self) -> None:
        self._az_text.side_effect = BoardError("403 Forbidden")
        ok, msg = await add_member_to_board_group("group-1", "user-1")
        assert ok is False
        assert "could not add" in msg.lower()
