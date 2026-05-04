"""Decorative boarding pass — Rich panel reproduction of ui_boarding_pass() from ui.sh."""

from __future__ import annotations

from rich.box import DOUBLE
from rich.panel import Panel
from rich.text import Text

from board.ui.console import ACCENT, console

# Bar characters used to build the decorative barcode
_BAR_CHARS = ("┃", "│", "┃", "│", "║", "│", "┃", "│")


def _make_barcode(name: str, width: int = 48) -> str:
    """Generate a deterministic decorative barcode string from a name."""
    chars: list[str] = []
    for i in range(1, width + 1):
        idx = (i * len(name)) % len(_BAR_CHARS)
        chars.append(_BAR_CHARS[idx])
    return "".join(chars)


def _truncate(text: str, max_len: int = 42) -> str:
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def render_boarding_pass(
    name: str,
    resource_group: str,
    region: str,
    hostname: str,
    auth_method: str,
    filename: str,
    issued_at: str,
    valid_until: str,
) -> None:
    """Render a decorative boarding pass to the console."""
    # Pull a 3-letter zone code from the region (e.g. australiaeast -> AUS).
    zone = region[:3].upper() if region else "---"
    issued_short = issued_at.split("T")[0] if "T" in issued_at else issued_at
    expiry_short = valid_until.split("T")[0] if "T" in valid_until else valid_until
    initials = name[:2].upper()
    host_display = _truncate(hostname)
    barcode = _make_barcode(name)

    perforation = "· " * 26  # ~52 chars of "· " pattern

    # Build the body text piece by piece
    body = Text()

    # Header line
    body.append("◆  B O A R D   P A S S", style=f"bold {ACCENT}")
    body.append("\n")
    body.append("ACCESS CREDENTIAL", style="dim")
    body.append("\n\n")

    # Identity: avatar + name
    body.append("[", style=ACCENT)
    body.append(initials, style=f"bold {ACCENT}")
    body.append("]", style=ACCENT)
    body.append(f"  {name}", style="bold")
    body.append("\n")
    body.append(f"     {resource_group}", style="dim")
    body.append("\n\n")

    # Row 1: labels
    body.append(f"{'REGION':<20}  {'AUTH METHOD':<18}  {'ZONE'}", style="dim")
    body.append("\n")
    # Row 1: values
    body.append(f"{region:<20}", style="bold")
    body.append(f"  {auth_method:<18}", style="bold")
    body.append(f"  {zone}", style=f"bold {ACCENT}")
    body.append("\n\n")

    # Row 2: host
    body.append("HOST", style="dim")
    body.append("\n")
    body.append(host_display, style="bold dim")
    body.append("\n\n")

    # Perforation
    body.append(perforation, style="dim")
    body.append("\n\n")

    # Row 3: labels
    body.append(f"{'ISSUED':<20}  {'EXPIRES':<18}  {'FILE'}", style="dim")
    body.append("\n")
    # Row 3: values
    body.append(f"{issued_short:<20}  {expiry_short:<18}  {filename}", style="bold")
    body.append("\n\n")

    # Barcode
    body.append(barcode, style=ACCENT)
    body.append("\n")
    body.append(filename, style="dim")

    console.print()
    console.print(Panel(body, border_style=ACCENT, box=DOUBLE, padding=(1, 2)))
    console.print()


__all__ = ["render_boarding_pass"]
