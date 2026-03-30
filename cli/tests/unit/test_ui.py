"""Tests for UI layer — console output, non-interactive prompts, boarding pass."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from board.ui.boarding_pass import render_boarding_pass
from board.ui.console import (
    ACCENT,
    BOARD_ASCII,
    BOARD_THEME,
    ascii_banner,
    banner,
    completion_box,
    divider,
    error,
    header,
    info,
    phase_timing,
    step,
    success,
    summary_box,
    warn,
    warn_summary,
)
from board.ui.prompts import (
    checklist,
    choose,
    confirm,
    input_text,
    input_validated,
    secret,
)

# ── Helpers ──


def _capture_console() -> tuple[Console, StringIO]:
    """Create a recording console that writes to a StringIO buffer."""
    buf = StringIO()
    c = Console(theme=BOARD_THEME, file=buf, record=True, width=100)
    return c, buf


# ── Console output tests ──


class TestConsoleTheme:
    def test_accent_colour(self) -> None:
        assert ACCENT == "#0ea5e9"

    def test_theme_has_expected_styles(self) -> None:
        assert "accent" in BOARD_THEME.styles
        assert "success" in BOARD_THEME.styles
        assert "error" in BOARD_THEME.styles
        assert "warn" in BOARD_THEME.styles
        assert "info" in BOARD_THEME.styles

    def test_ascii_art_present(self) -> None:
        assert "██████╗" in BOARD_ASCII
        assert "╚═════╝" in BOARD_ASCII


class TestConsoleOutput:
    """Verify each display function renders without error.

    We patch board.ui.console.console with a recording console so
    output goes to a StringIO rather than the real terminal.
    """

    def _make_console(self) -> tuple[Console, StringIO]:
        buf = StringIO()
        c = Console(theme=BOARD_THEME, file=buf, record=True, width=100)
        return c, buf

    def test_header(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            header("Test Header")
        output = buf.getvalue()
        assert "Test Header" in output

    def test_banner(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            banner("Board", "Developer VM Provisioning")
        output = buf.getvalue()
        assert "Board" in output
        assert "Developer VM Provisioning" in output

    def test_ascii_banner(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            ascii_banner("Developer VM Provisioning")
        output = buf.getvalue()
        assert "██████╗" in output
        assert "Developer VM Provisioning" in output

    def test_step(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            step(1, 5, "Configure")
        output = buf.getvalue()
        assert "1/5" in output
        assert "Configure" in output

    def test_success(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            success("All good")
        output = buf.getvalue()
        assert "✓" in output
        assert "All good" in output

    def test_error(self) -> None:
        c, buf = self._make_console()
        # error() writes to _stderr_console, so patch that
        with patch("board.ui.console._stderr_console", c):
            error("Something failed")
        output = buf.getvalue()
        assert "✗" in output
        assert "Something failed" in output

    def test_warn(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            warn("Watch out")
        output = buf.getvalue()
        assert "!" in output
        assert "Watch out" in output

    def test_info(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            info("Some detail")
        output = buf.getvalue()
        assert "Some detail" in output

    def test_divider(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            divider()
        output = buf.getvalue()
        # Rich rule uses ─ characters
        assert "─" in output

    def test_summary_box(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            summary_box("Summary", ["Region: australiaeast", "VM: Standard_D4s_v5"])
        output = buf.getvalue()
        assert "Summary" in output
        assert "australiaeast" in output

    def test_completion_box(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            completion_box("Done", ["VM deployed", "SSH configured"])
        output = buf.getvalue()
        assert "Done" in output
        assert "VM deployed" in output

    def test_warn_summary_with_warnings(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            warn_summary("Warnings", ["Disk nearly full", "Old SSH key"])
        output = buf.getvalue()
        assert "Warnings (2)" in output
        assert "Disk nearly full" in output
        assert "Old SSH key" in output

    def test_warn_summary_empty(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            warn_summary("Warnings", [])
        output = buf.getvalue()
        # Empty warnings should produce no output
        assert output == ""

    def test_phase_timing(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            phase_timing("Infrastructure deployed", 222)
        output = buf.getvalue()
        assert "Infrastructure deployed" in output
        assert "3m 42s" in output

    def test_phase_timing_seconds_only(self) -> None:
        c, buf = self._make_console()
        with patch("board.ui.console.console", c):
            phase_timing("Quick step", 7)
        output = buf.getvalue()
        assert "Quick step" in output
        assert "7s" in output


# ── Non-interactive prompt tests ──


class TestNonInteractivePrompts:
    """With BOARD_NON_INTERACTIVE=1, prompts must skip interaction and return fallbacks."""

    @pytest.fixture(autouse=True)
    def _set_non_interactive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BOARD_NON_INTERACTIVE", "1")

    def test_input_text_returns_default(self) -> None:
        assert input_text("Name", default="jbloggs") == "jbloggs"

    def test_input_text_empty_default(self) -> None:
        assert input_text("Name") == ""

    def test_input_validated_returns_default(self) -> None:
        result = input_validated(
            "Developer name",
            default="jbloggs",
            pattern=r"^[a-z][a-z0-9]{0,11}$",
            message="Invalid name",
        )
        assert result == "jbloggs"

    def test_choose_returns_default(self) -> None:
        assert (
            choose("Region", ["australiaeast", "eastus"], default="australiaeast")
            == "australiaeast"
        )

    def test_choose_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BOARD_REGION", "eastus")
        assert (
            choose("Select region", ["australiaeast", "eastus"], default="australiaeast")
            == "eastus"
        )

    def test_choose_env_override_invalid_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BOARD_REGION", "nosuchregion")
        result = choose("Select region", ["australiaeast", "eastus"], default="australiaeast")
        assert result == "australiaeast"

    def test_choose_falls_back_to_first(self) -> None:
        assert choose("Region", ["australiaeast", "eastus"]) == "australiaeast"

    def test_checklist_returns_defaults(self) -> None:
        result = checklist("Projects", ["surf", "surf-kit", "myterm"], defaults=["surf"])
        assert result == ["surf"]

    def test_checklist_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BOARD_PROJECTS", "surf myterm")
        result = checklist("Projects", ["surf", "surf-kit", "myterm"], defaults=["surf"])
        assert result == ["surf", "myterm"]

    def test_checklist_empty_defaults(self) -> None:
        result = checklist("Projects", ["surf", "surf-kit"])
        assert result == []

    def test_confirm_returns_true(self) -> None:
        assert confirm("Continue?") is True

    def test_confirm_ignores_default(self) -> None:
        assert confirm("Continue?", default=False) is True

    def test_secret_returns_empty(self) -> None:
        assert secret("Token") == ""


# ── Boarding pass tests ──


class TestBoardingPass:
    def _render(self, **overrides: str) -> str:
        defaults = {
            "name": "jbloggs",
            "environment": "personal",
            "region": "australiaeast",
            "region_short": "aue",
            "hostname": "devvm-jbloggs.australiaeast.cloudapp.azure.com",
            "auth_method": "SSH Key",
            "filename": "jbloggs.board",
            "issued_at": "2026-03-29T00:00:00Z",
            "valid_until": "2026-04-28T00:00:00Z",
        }
        defaults.update(overrides)

        buf = StringIO()
        c = Console(theme=BOARD_THEME, file=buf, record=True, width=100)
        with patch("board.ui.boarding_pass.console", c):
            render_boarding_pass(**defaults)
        return buf.getvalue()

    def test_renders_without_error(self) -> None:
        output = self._render()
        assert len(output) > 0

    def test_contains_header(self) -> None:
        output = self._render()
        assert "B O A R D   P A S S" in output
        assert "ACCESS CREDENTIAL" in output

    def test_contains_initials(self) -> None:
        output = self._render()
        assert "JB" in output

    def test_contains_name(self) -> None:
        output = self._render()
        assert "jbloggs" in output

    def test_contains_environment(self) -> None:
        output = self._render()
        assert "personal environment" in output

    def test_contains_region(self) -> None:
        output = self._render()
        assert "australiaeast" in output

    def test_contains_zone(self) -> None:
        output = self._render()
        assert "AUE" in output

    def test_contains_auth_method(self) -> None:
        output = self._render()
        assert "SSH Key" in output

    def test_contains_hostname(self) -> None:
        output = self._render()
        assert "devvm-jbloggs" in output

    def test_contains_dates(self) -> None:
        output = self._render()
        assert "2026-03-29" in output
        assert "2026-04-28" in output

    def test_contains_filename(self) -> None:
        output = self._render()
        assert "jbloggs.board" in output

    def test_contains_barcode(self) -> None:
        output = self._render()
        # Barcode uses pipe-like chars
        assert "┃" in output or "│" in output or "║" in output

    def test_contains_perforation(self) -> None:
        output = self._render()
        assert "· ·" in output

    def test_long_hostname_truncated(self) -> None:
        long_host = "devvm-jbloggs.australiaeast.cloudapp.azure.com.extra.subdomain"
        output = self._render(hostname=long_host)
        assert "..." in output

    def test_date_without_time_component(self) -> None:
        output = self._render(issued_at="2026-03-29", valid_until="2026-04-28")
        assert "2026-03-29" in output
        assert "2026-04-28" in output
