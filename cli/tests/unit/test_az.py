"""Tests for board.azure.az — safe async CLI runner."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from board.azure.az import az_json, az_text
from board.core.errors import BoardError


def _mock_proc(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> MagicMock:
    """Create a mock subprocess with given outputs."""
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


class TestAzText:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        proc = _mock_proc(stdout=b"  some-value\n  ")
        with patch("board.azure.az.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            result = await az_text("account", "show", "--query", "id", "-o", "tsv")

        assert result == "some-value"

    @pytest.mark.asyncio
    async def test_nonzero_exit_raises(self) -> None:
        proc = _mock_proc(stderr=b"ERROR: not logged in", returncode=1)
        with (
            patch("board.azure.az.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
            pytest.raises(BoardError, match="az account failed: ERROR: not logged in"),
        ):
            await az_text("account", "show")

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self) -> None:
        proc = _mock_proc()
        proc.communicate = AsyncMock(side_effect=TimeoutError)
        with (
            patch("board.azure.az.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
            pytest.raises(BoardError, match="timed out after 5s"),
        ):
            await az_text("account", "show", timeout=5)

        proc.kill.assert_called_once()
        proc.wait.assert_awaited_once()


class TestAzJson:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        proc = _mock_proc(stdout=b'{"id": "sub-123", "name": "My Sub"}')
        with patch("board.azure.az.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            result = await az_json("account", "show", "-o", "json")

        assert result == {"id": "sub-123", "name": "My Sub"}

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self) -> None:
        proc = _mock_proc(stdout=b"not json at all")
        with (
            patch("board.azure.az.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
            pytest.raises(BoardError, match="invalid JSON"),
        ):
            await az_json("account", "list")
