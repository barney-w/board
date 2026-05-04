"""Tests for board.azure.vm_tags — auth-method tag resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from board.azure.vm_tags import resolve_auth_method
from board.core.errors import BoardError


def _mock_run(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    result = MagicMock()
    result.stdout = stdout
    result.stderr = stderr
    result.returncode = returncode
    return result


class TestResolveAuthMethod:
    def test_returns_entra_id(self) -> None:
        with patch(
            "board.azure.vm_tags.subprocess.run",
            return_value=_mock_run(stdout="entra-id\n"),
        ):
            assert resolve_auth_method("rg-vibe", "vm-vibe-aivm1") == "entra-id"

    def test_returns_ssh_key(self) -> None:
        with patch(
            "board.azure.vm_tags.subprocess.run",
            return_value=_mock_run(stdout="ssh-key\n"),
        ):
            assert resolve_auth_method("rg-vibe", "vm-vibe-foo") == "ssh-key"

    def test_az_failure_raises_boarderror(self) -> None:
        with (
            patch(
                "board.azure.vm_tags.subprocess.run",
                return_value=_mock_run(stderr="ERROR: ResourceNotFound", returncode=3),
            ),
            pytest.raises(BoardError, match=r"Could not read VM tags"),
        ):
            resolve_auth_method("rg-vibe", "vm-vibe-missing")

    def test_missing_tag_raises_boarderror(self) -> None:
        with (
            patch(
                "board.azure.vm_tags.subprocess.run",
                return_value=_mock_run(stdout="\n"),
            ),
            pytest.raises(BoardError, match="has no 'auth-method' tag"),
        ):
            resolve_auth_method("rg-vibe", "vm-vibe-untagged")

    def test_invalid_tag_raises_boarderror(self) -> None:
        with (
            patch(
                "board.azure.vm_tags.subprocess.run",
                return_value=_mock_run(stdout="oauth\n"),
            ),
            pytest.raises(BoardError, match="unrecognised 'auth-method' tag"),
        ):
            resolve_auth_method("rg-vibe", "vm-vibe-typo")

    def test_error_message_mentions_remediation(self) -> None:
        with patch(
            "board.azure.vm_tags.subprocess.run",
            return_value=_mock_run(stdout=""),
        ):
            try:
                resolve_auth_method("rg-vibe", "vm-vibe-untagged")
            except BoardError as exc:
                msg = str(exc)
                assert "az vm update" in msg
                assert "--auth entra-id" in msg or "--auth ssh-key" in msg
            else:
                pytest.fail("BoardError was not raised")
