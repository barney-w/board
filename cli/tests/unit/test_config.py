"""Tests for naming conventions — must match extension/src/config.ts exactly."""

import pytest

from board.core.config import (
    hostname,
    resource_group,
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

    def test_resource_group(self) -> None:
        assert resource_group("personal", "aue") == "rg-personal-aue-devvm"

    def test_vm_name(self) -> None:
        assert vm_name("personal", "aue", "jbloggs") == "vm-personal-aue-devvm-jbloggs"

    def test_ssh_key_path(self) -> None:
        assert ssh_key_path("jbloggs") == "~/.ssh/devvm-jbloggs"

    def test_tunnel_url_derived(self) -> None:
        assert tunnel_url("jbloggs") == "https://vscode.dev/tunnel/devvm-jbloggs"

    def test_tunnel_url_explicit(self) -> None:
        assert tunnel_url("jbloggs", "https://custom.url") == "https://custom.url"

    def test_tunnel_url_empty_name(self) -> None:
        assert tunnel_url("") == ""

    # Multiple input sets for comprehensive coverage
    @pytest.mark.parametrize(
        "name,env,region,rshort",
        [
            ("jbloggs", "personal", "australiaeast", "aue"),
            ("asmith", "sandbox", "eastus", "eus"),
            ("cjones", "personal", "westeurope", "weu"),
        ],
    )
    def test_all_derivations(self, name: str, env: str, region: str, rshort: str) -> None:
        assert ssh_host_alias(name) == f"devvm-{name}"
        assert hostname(name, region) == f"devvm-{name}.{region}.cloudapp.azure.com"
        assert resource_group(env, rshort) == f"rg-{env}-{rshort}-devvm"
        assert vm_name(env, rshort, name) == f"vm-{env}-{rshort}-devvm-{name}"
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
