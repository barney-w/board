"""Tests for board.core.policies and board.models.policies."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from board.core import policies as pol
from board.core.errors import PolicyViolationError
from board.models.policies import PoliciesConfig


class TestPoliciesConfig:
    """Pydantic model validation."""

    def test_defaults(self) -> None:
        cfg = PoliciesConfig()
        assert cfg.max_vms_per_user == 1
        assert cfg.max_vms_total == 20
        assert cfg.require_entra_auth is True
        assert "Standard_D2s_v6" in cfg.allowed_vm_sizes
        assert "australiaeast" in cfg.allowed_regions

    def test_custom_values(self) -> None:
        cfg = PoliciesConfig(
            max_vms_per_user=3,
            allowed_vm_sizes=["Standard_E16s_v5"],
            allowed_regions=["westus2", "australiaeast"],
            require_entra_auth=False,
        )
        assert cfg.max_vms_per_user == 3
        assert cfg.allowed_vm_sizes == ["Standard_E16s_v5"]
        assert cfg.require_entra_auth is False


class TestFindPoliciesFile:
    """File discovery."""

    def test_finds_file(self, tmp_path: Path) -> None:
        policies_file = tmp_path / "board.policies.yaml"
        policies_file.write_text("max_vms_per_user: 5\n")
        with patch("board.core.policies.Path.cwd", return_value=tmp_path):
            found = pol.find_policies_file()
        assert found == policies_file

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        with patch("board.core.policies.Path.cwd", return_value=tmp_path):
            found = pol.find_policies_file()
        assert found is None


class TestLoad:
    """YAML loading."""

    def test_load_from_file(self, tmp_path: Path) -> None:
        policies_file = tmp_path / "board.policies.yaml"
        policies_file.write_text(
            "max_vms_per_user: 2\nallowed_regions:\n  - westus2\n"
        )
        cfg = pol.load(policies_file)
        assert cfg is not None
        assert cfg.max_vms_per_user == 2
        assert cfg.allowed_regions == ["westus2"]

    def test_load_returns_none_when_missing(self) -> None:
        assert pol.load(Path("/nonexistent/path/board.policies.yaml")) is None


class TestEnforce:
    """Policy enforcement logic."""

    @pytest.fixture()
    def default_policies(self) -> PoliciesConfig:
        return PoliciesConfig()

    @staticmethod
    def _enforce(policies: PoliciesConfig, **overrides: str) -> list[str]:
        defaults = {
            "vm_sku": "Standard_D2s_v6",
            "region": "australiaeast",
            "auth_method": "entra-id",
            "developer_name": "jbloggs",
            "resource_group": "rg-nonexistent",
        }
        defaults.update(overrides)
        return pol.enforce(policies, **defaults)

    def test_valid_config_passes(self, default_policies: PoliciesConfig) -> None:
        warnings = self._enforce(default_policies)
        assert warnings == []

    def test_disallowed_vm_size(self, default_policies: PoliciesConfig) -> None:
        with pytest.raises(PolicyViolationError, match="VM size"):
            self._enforce(default_policies, vm_sku="Standard_E96s_v5")

    def test_disallowed_region(self, default_policies: PoliciesConfig) -> None:
        with pytest.raises(PolicyViolationError, match="Region"):
            self._enforce(default_policies, region="westus2")

    def test_ssh_key_blocked_when_entra_required(
        self, default_policies: PoliciesConfig
    ) -> None:
        with pytest.raises(PolicyViolationError, match="Entra ID"):
            self._enforce(default_policies, auth_method="ssh-key")

    def test_ssh_key_allowed_when_not_required(self) -> None:
        cfg = PoliciesConfig(require_entra_auth=False)
        warnings = self._enforce(cfg, auth_method="ssh-key")
        assert warnings == []

    def test_multiple_violations_reported(
        self, default_policies: PoliciesConfig
    ) -> None:
        with pytest.raises(PolicyViolationError) as exc_info:
            self._enforce(
                default_policies,
                vm_sku="Standard_E96s_v5",
                region="westus2",
                auth_method="ssh-key",
            )
        msg = str(exc_info.value)
        assert "VM size" in msg
        assert "Region" in msg
        assert "Entra ID" in msg
