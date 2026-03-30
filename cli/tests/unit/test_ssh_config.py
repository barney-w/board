"""Tests for SSH config managed block operations.

Verifies the block format matches extension/src/ssh.ts exactly,
and that insert/replace/remove operations are correct.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from board.ssh.config_file import (
    build_ssh_key_config_block,
    read_managed_block,
    remove_managed_block,
    write_managed_block,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def ssh_config(tmp_path: Path) -> Path:
    """Path to a temporary SSH config file (doesn't exist yet)."""
    return tmp_path / ".ssh" / "config"


class TestBuildSshKeyConfigBlock:
    """Block content must match extension/src/ssh.ts buildSshKeyConfigBlock."""

    def test_block_format_matches_extension(self) -> None:
        block = build_ssh_key_config_block(
            alias="devvm-jbloggs",
            hostname="devvm-jbloggs.australiaeast.cloudapp.azure.com",
            key_path="~/.ssh/devvm-jbloggs",
        )
        expected = "\n".join(
            [
                "Host devvm-jbloggs",
                "    HostName devvm-jbloggs.australiaeast.cloudapp.azure.com",
                "    User devuser",
                "    IdentityFile ~/.ssh/devvm-jbloggs",
                "    ForwardAgent yes",
                "    ServerAliveInterval 60",
                "    ServerAliveCountMax 3",
                "    StrictHostKeyChecking accept-new",
            ]
        )
        assert block == expected

    def test_custom_username(self) -> None:
        block = build_ssh_key_config_block(
            alias="devvm-test",
            hostname="1.2.3.4",
            key_path="~/.ssh/devvm-test",
            username="admin",
        )
        assert "    User admin" in block

    def test_uses_four_space_indent(self) -> None:
        """Extension uses 4-space indent, not tabs."""
        block = build_ssh_key_config_block(
            alias="devvm-x",
            hostname="h",
            key_path="k",
        )
        for line in block.split("\n")[1:]:
            assert line.startswith("    "), f"Line should start with 4 spaces: {line!r}"
            assert not line.startswith("\t"), f"Line should not use tabs: {line!r}"


class TestWriteManagedBlock:
    def test_insert_into_new_file(self, ssh_config: Path) -> None:
        """Writing to a non-existent file should create it."""
        block = build_ssh_key_config_block(
            alias="devvm-jbloggs",
            hostname="devvm-jbloggs.australiaeast.cloudapp.azure.com",
            key_path="~/.ssh/devvm-jbloggs",
        )
        write_managed_block(ssh_config, "devvm-jbloggs", block)

        assert ssh_config.exists()
        content = ssh_config.read_text()
        assert "# BEGIN board: devvm-jbloggs" in content
        assert "# END board: devvm-jbloggs" in content
        assert "Host devvm-jbloggs" in content
        assert "    HostName devvm-jbloggs.australiaeast.cloudapp.azure.com" in content

    def test_insert_preserves_existing_content(self, ssh_config: Path) -> None:
        """Existing SSH config entries should not be disturbed."""
        ssh_config.parent.mkdir(parents=True, exist_ok=True)
        existing = (
            "Host github.com\n"
            "    HostName github.com\n"
            "    User git\n"
            "    IdentityFile ~/.ssh/id_ed25519\n"
        )
        ssh_config.write_text(existing)

        block = build_ssh_key_config_block(
            alias="devvm-jbloggs",
            hostname="devvm-jbloggs.australiaeast.cloudapp.azure.com",
            key_path="~/.ssh/devvm-jbloggs",
        )
        write_managed_block(ssh_config, "devvm-jbloggs", block)

        content = ssh_config.read_text()
        # Existing content preserved
        assert "Host github.com" in content
        assert "    User git" in content
        # New block added
        assert "# BEGIN board: devvm-jbloggs" in content
        assert "Host devvm-jbloggs" in content
        assert "# END board: devvm-jbloggs" in content

    def test_replace_existing_block(self, ssh_config: Path) -> None:
        """Replacing a block should update content between markers."""
        block_v1 = build_ssh_key_config_block(
            alias="devvm-jbloggs",
            hostname="old-host.cloudapp.azure.com",
            key_path="~/.ssh/devvm-jbloggs",
        )
        write_managed_block(ssh_config, "devvm-jbloggs", block_v1)

        # Now update with new hostname
        block_v2 = build_ssh_key_config_block(
            alias="devvm-jbloggs",
            hostname="new-host.cloudapp.azure.com",
            key_path="~/.ssh/devvm-jbloggs",
        )
        write_managed_block(ssh_config, "devvm-jbloggs", block_v2)

        content = ssh_config.read_text()
        # Old content gone, new content present
        assert "old-host.cloudapp.azure.com" not in content
        assert "new-host.cloudapp.azure.com" in content
        # Only one block
        assert content.count("# BEGIN board: devvm-jbloggs") == 1
        assert content.count("# END board: devvm-jbloggs") == 1

    def test_multiple_blocks_independent(self, ssh_config: Path) -> None:
        """Multiple aliases can coexist without interfering."""
        block_a = build_ssh_key_config_block(
            alias="devvm-alice",
            hostname="alice.cloudapp.azure.com",
            key_path="~/.ssh/devvm-alice",
        )
        block_b = build_ssh_key_config_block(
            alias="devvm-bob",
            hostname="bob.cloudapp.azure.com",
            key_path="~/.ssh/devvm-bob",
        )
        write_managed_block(ssh_config, "devvm-alice", block_a)
        write_managed_block(ssh_config, "devvm-bob", block_b)

        content = ssh_config.read_text()
        assert "# BEGIN board: devvm-alice" in content
        assert "# END board: devvm-alice" in content
        assert "# BEGIN board: devvm-bob" in content
        assert "# END board: devvm-bob" in content
        assert "alice.cloudapp.azure.com" in content
        assert "bob.cloudapp.azure.com" in content

    def test_file_permissions(self, ssh_config: Path) -> None:
        """SSH config file should be created with 0600 permissions."""
        block = build_ssh_key_config_block(
            alias="devvm-test",
            hostname="test.com",
            key_path="~/.ssh/devvm-test",
        )
        write_managed_block(ssh_config, "devvm-test", block)

        mode = ssh_config.stat().st_mode & 0o777
        assert mode == 0o600

    def test_insert_into_empty_file(self, ssh_config: Path) -> None:
        """Writing to an empty existing file should work."""
        ssh_config.parent.mkdir(parents=True, exist_ok=True)
        ssh_config.write_text("")

        block = build_ssh_key_config_block(
            alias="devvm-test",
            hostname="test.com",
            key_path="~/.ssh/devvm-test",
        )
        write_managed_block(ssh_config, "devvm-test", block)

        content = ssh_config.read_text()
        assert "# BEGIN board: devvm-test" in content
        assert "# END board: devvm-test" in content


class TestReadManagedBlock:
    def test_read_existing_block(self, ssh_config: Path) -> None:
        block = build_ssh_key_config_block(
            alias="devvm-jbloggs",
            hostname="devvm-jbloggs.australiaeast.cloudapp.azure.com",
            key_path="~/.ssh/devvm-jbloggs",
        )
        write_managed_block(ssh_config, "devvm-jbloggs", block)

        result = read_managed_block(ssh_config, "devvm-jbloggs")
        assert result is not None
        assert "# BEGIN board: devvm-jbloggs" in result
        assert "Host devvm-jbloggs" in result
        assert "# END board: devvm-jbloggs" in result

    def test_read_missing_block(self, ssh_config: Path) -> None:
        ssh_config.parent.mkdir(parents=True, exist_ok=True)
        ssh_config.write_text("Host other\n    HostName other.com\n")

        result = read_managed_block(ssh_config, "devvm-nonexistent")
        assert result is None

    def test_read_missing_file(self, ssh_config: Path) -> None:
        result = read_managed_block(ssh_config, "devvm-jbloggs")
        assert result is None


class TestRemoveManagedBlock:
    def test_remove_existing_block(self, ssh_config: Path) -> None:
        block = build_ssh_key_config_block(
            alias="devvm-jbloggs",
            hostname="devvm-jbloggs.australiaeast.cloudapp.azure.com",
            key_path="~/.ssh/devvm-jbloggs",
        )
        write_managed_block(ssh_config, "devvm-jbloggs", block)
        assert ssh_config.read_text().count("devvm-jbloggs") > 0

        removed = remove_managed_block(ssh_config, "devvm-jbloggs")
        assert removed is True

        content = ssh_config.read_text()
        assert "devvm-jbloggs" not in content

    def test_remove_preserves_other_content(self, ssh_config: Path) -> None:
        ssh_config.parent.mkdir(parents=True, exist_ok=True)
        existing = "Host github.com\n    HostName github.com\n    User git\n"
        ssh_config.write_text(existing)

        block = build_ssh_key_config_block(
            alias="devvm-jbloggs",
            hostname="test.com",
            key_path="~/.ssh/devvm-jbloggs",
        )
        write_managed_block(ssh_config, "devvm-jbloggs", block)

        removed = remove_managed_block(ssh_config, "devvm-jbloggs")
        assert removed is True

        content = ssh_config.read_text()
        assert "Host github.com" in content
        assert "    User git" in content
        assert "devvm-jbloggs" not in content

    def test_remove_missing_block_returns_false(self, ssh_config: Path) -> None:
        ssh_config.parent.mkdir(parents=True, exist_ok=True)
        ssh_config.write_text("Host other\n    HostName other.com\n")

        removed = remove_managed_block(ssh_config, "devvm-nonexistent")
        assert removed is False

    def test_remove_from_missing_file(self, ssh_config: Path) -> None:
        removed = remove_managed_block(ssh_config, "devvm-jbloggs")
        assert removed is False

    def test_remove_one_of_multiple_blocks(self, ssh_config: Path) -> None:
        """Removing one block should leave other blocks intact."""
        block_a = build_ssh_key_config_block(
            alias="devvm-alice",
            hostname="alice.com",
            key_path="~/.ssh/devvm-alice",
        )
        block_b = build_ssh_key_config_block(
            alias="devvm-bob",
            hostname="bob.com",
            key_path="~/.ssh/devvm-bob",
        )
        write_managed_block(ssh_config, "devvm-alice", block_a)
        write_managed_block(ssh_config, "devvm-bob", block_b)

        removed = remove_managed_block(ssh_config, "devvm-alice")
        assert removed is True

        content = ssh_config.read_text()
        assert "devvm-alice" not in content
        assert "# BEGIN board: devvm-bob" in content
        assert "bob.com" in content
        assert "# END board: devvm-bob" in content


class TestMarkerFormat:
    """Verify marker format matches extension/src/ssh.ts exactly."""

    def test_begin_marker_format(self, ssh_config: Path) -> None:
        """Marker must be: # BEGIN board: {alias} (with space after colon)."""
        block = build_ssh_key_config_block(
            alias="devvm-jbloggs",
            hostname="h",
            key_path="k",
        )
        write_managed_block(ssh_config, "devvm-jbloggs", block)
        content = ssh_config.read_text()
        # Extension uses: MARKER_PREFIX = '# BEGIN board:'
        # Then: `${MARKER_PREFIX} ${hostAlias}`
        assert "# BEGIN board: devvm-jbloggs" in content

    def test_end_marker_format(self, ssh_config: Path) -> None:
        """Marker must be: # END board: {alias} (with space after colon)."""
        block = build_ssh_key_config_block(
            alias="devvm-jbloggs",
            hostname="h",
            key_path="k",
        )
        write_managed_block(ssh_config, "devvm-jbloggs", block)
        content = ssh_config.read_text()
        assert "# END board: devvm-jbloggs" in content

    def test_full_block_structure(self, ssh_config: Path) -> None:
        """Full block layout: BEGIN marker, Host stanza, END marker."""
        block = build_ssh_key_config_block(
            alias="devvm-jbloggs",
            hostname="devvm-jbloggs.australiaeast.cloudapp.azure.com",
            key_path="~/.ssh/devvm-jbloggs",
        )
        write_managed_block(ssh_config, "devvm-jbloggs", block)
        content = ssh_config.read_text()

        lines = content.strip().split("\n")
        assert lines[0] == "# BEGIN board: devvm-jbloggs"
        assert lines[1] == "Host devvm-jbloggs"
        assert lines[2] == "    HostName devvm-jbloggs.australiaeast.cloudapp.azure.com"
        assert lines[3] == "    User devuser"
        assert lines[4] == "    IdentityFile ~/.ssh/devvm-jbloggs"
        assert lines[5] == "    ForwardAgent yes"
        assert lines[6] == "    ServerAliveInterval 60"
        assert lines[7] == "    ServerAliveCountMax 3"
        assert lines[8] == "    StrictHostKeyChecking accept-new"
        assert lines[9] == "# END board: devvm-jbloggs"
