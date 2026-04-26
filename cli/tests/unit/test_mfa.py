"""Tests for board.azure.mfa — Conditional Access MFA policy management."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from board.azure.mfa import (
    _POLICY_DISPLAY_NAME,
    _resolve_vm_signin_app_id,
    ensure_mfa_policy,
    find_existing_policy,
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


class TestEnsureMfaPolicy:
    """Policy creation."""

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

    async def test_creates_policy_when_none_exists(self) -> None:
        ok, msg = await ensure_mfa_policy()
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

    async def test_skips_when_policy_exists(self) -> None:
        self._find.return_value = {
            "displayName": _POLICY_DISPLAY_NAME,
            "state": "enabled",
        }
        ok, msg = await ensure_mfa_policy()
        assert ok is True
        assert "already exists" in msg.lower()
        self._az_text.assert_not_called()

    async def test_handles_permission_error(self) -> None:
        self._az_text.side_effect = BoardError("az rest failed: 403 Forbidden")
        ok, msg = await ensure_mfa_policy()
        assert ok is False
        assert "Conditional Access Administrator" in msg

    async def test_handles_generic_error(self) -> None:
        self._az_text.side_effect = BoardError("az rest failed: network timeout")
        ok, msg = await ensure_mfa_policy()
        assert ok is False
        assert "network timeout" in msg.lower()
