"""Tests for naming conventions — must match extension/src/config.ts exactly."""

import pytest

from board.core.config import (
    hostname,
    rg_suffix,
    ssh_host_alias,
    ssh_key_path,
    tunnel_url,
    validate_developer_name,
    vm_name,
)


class TestNamingConventions:
    """All naming derivations must produce strings identical to the extension."""

    def test_ssh_host_alias(self) -> None:
        assert ssh_host_alias("jbloggs") == "devvm-jbloggs"

    def test_hostname(self) -> None:
        assert (
            hostname("jbloggs", "australiaeast") == "devvm-jbloggs.australiaeast.cloudapp.azure.com"
        )

    def test_rg_suffix_strips_rg_prefix(self) -> None:
        assert rg_suffix("rg-platform-prod") == "platform-prod"
        assert rg_suffix("rg-dev-aue-devvm") == "dev-aue-devvm"

    def test_rg_suffix_passthrough(self) -> None:
        """If the RG name doesn't start with 'rg-', use it as-is."""
        assert rg_suffix("my-team") == "my-team"
        assert rg_suffix("platform_prod") == "platform_prod"

    def test_vm_name(self) -> None:
        assert vm_name("rg-platform-prod", "jbloggs") == "vm-platform-prod-jbloggs"
        assert vm_name("my-team", "jbloggs") == "vm-my-team-jbloggs"

    def test_ssh_key_path(self) -> None:
        assert ssh_key_path("jbloggs") == "~/.ssh/devvm-jbloggs"

    def test_tunnel_url_derived(self) -> None:
        assert tunnel_url("jbloggs") == "https://vscode.dev/tunnel/devvm-jbloggs"

    def test_tunnel_url_explicit(self) -> None:
        assert tunnel_url("jbloggs", "https://custom.url") == "https://custom.url"

    def test_tunnel_url_empty_name(self) -> None:
        assert tunnel_url("") == ""

    @pytest.mark.parametrize(
        "name,rg,region",
        [
            ("jbloggs", "rg-personal-aue-devvm", "australiaeast"),
            ("asmith", "rg-sandbox-eus-devvm", "eastus"),
            ("cjones", "platform-prod", "westeurope"),
        ],
    )
    def test_all_derivations(self, name: str, rg: str, region: str) -> None:
        suffix = rg.removeprefix("rg-")
        assert ssh_host_alias(name) == f"devvm-{name}"
        assert hostname(name, region) == f"devvm-{name}.{region}.cloudapp.azure.com"
        assert vm_name(rg, name) == f"vm-{suffix}-{name}"
        assert ssh_key_path(name) == f"~/.ssh/devvm-{name}"


class TestDeveloperNameValidation:
    def test_valid_names(self) -> None:
        assert validate_developer_name("jbloggs")
        assert validate_developer_name("a")
        assert validate_developer_name("asmith")
        assert validate_developer_name("x123456789ab")  # 12 chars

    def test_invalid_names(self) -> None:
        assert not validate_developer_name("")
        assert not validate_developer_name("1abc")  # starts with digit
        assert not validate_developer_name("ABC")  # uppercase
        assert not validate_developer_name("a-b")  # hyphen
        assert not validate_developer_name("a_b")  # underscore
        assert not validate_developer_name("a123456789abc")  # 13 chars
