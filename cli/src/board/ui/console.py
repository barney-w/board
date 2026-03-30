"""Rich console wrapper — themed output functions for Board CLI.

Mirrors the display functions from scripts/lib/ui.sh using Rich panels,
styled text, and spinners instead of gum/ANSI escape codes.
"""

from __future__ import annotations

import asyncio
import platform
import subprocess
import time
from contextlib import asynccontextmanager, contextmanager, suppress
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich.theme import Theme

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

# ── Brand theme ──

ACCENT = "#0ea5e9"  # Sky-500

BOARD_THEME = Theme(
    {
        "accent": f"bold {ACCENT}",
        "accent.dim": ACCENT,
        "success": "green",
        "error": "red",
        "warn": "yellow",
        "info": "dim",
    }
)

console = Console(theme=BOARD_THEME)
_stderr_console = Console(theme=BOARD_THEME, stderr=True)

# ── ASCII art ──

BOARD_ASCII = (
    "██████╗  ██████╗  █████╗ ██████╗ ██████╗ \n"
    "██╔══██╗██╔═══██╗██╔══██╗██╔══██╗██╔══██╗\n"
    "██████╔╝██║   ██║███████║██████╔╝██║  ██║\n"
    "██╔══██╗██║   ██║██╔══██║██╔══██╗██║  ██║\n"
    "██████╔╝╚██████╔╝██║  ██║██║  ██║██████╔╝\n"
    "╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ "
)


# ── Display functions ──


def header(text: str) -> None:
    """Bold accent header text."""
    console.print()
    console.print(f"[accent]{text}[/accent]")
    console.print()


def banner(title: str, tagline: str) -> None:
    """Double-border panel with title and tagline."""
    body = Text()
    body.append(title, style=f"bold {ACCENT}")
    body.append("\n\n")
    body.append(tagline, style="dim")
    console.print()
    console.print(Panel(body, border_style=ACCENT, box=_DOUBLE_BOX, padding=(1, 3)))
    console.print()


def ascii_banner(tagline: str) -> None:
    """ASCII block-letter banner with tagline, inside a double-border panel."""
    body = Text()
    body.append(BOARD_ASCII, style=f"bold {ACCENT}")
    body.append("\n")
    body.append(f"  {tagline}", style="dim")
    console.print()
    console.print(Panel(body, border_style=ACCENT, box=_DOUBLE_BOX, padding=(1, 3)))
    console.print()


def step(current: int, total: int, text: str) -> None:
    """Phase counter: [1/5] Configure."""
    console.print(f"[accent]\\[{current}/{total}][/accent] [bold]{text}[/bold]")
    console.print()


def success(text: str) -> None:
    """Green checkmark message."""
    console.print(f"  [success]✓[/success] {text}")


def error(text: str) -> None:
    """Red cross message (to stderr)."""
    _stderr_console.print(f"  [error]✗[/error] {text}")


def warn(text: str) -> None:
    """Yellow exclamation message."""
    console.print(f"  [warn]![/warn] {text}")


def info(text: str) -> None:
    """Dim informational message."""
    console.print(f"  [info]{text}[/info]")


def divider() -> None:
    """Horizontal rule."""
    console.print(Rule(style="dim"))


def summary_box(title: str, lines: list[str]) -> None:
    """Rounded-border panel with sky-500 accent."""
    body = Text()
    for i, line in enumerate(lines):
        if i > 0:
            body.append("\n")
        body.append(f"  {line}")
    content = Text()
    content.append(title, style="bold")
    content.append("\n\n")
    content.append(body)
    console.print(Panel(content, border_style=ACCENT, box=_ROUNDED_BOX, padding=(0, 2)))
    console.print()


def completion_box(title: str, lines: list[str]) -> None:
    """Double-border panel with sky-500 accent."""
    body = Text()
    for i, line in enumerate(lines):
        if i > 0:
            body.append("\n")
        body.append(f"  {line}")
    content = Text()
    content.append(title, style="bold")
    content.append("\n\n")
    content.append(body)
    console.print(Panel(content, border_style=ACCENT, box=_DOUBLE_BOX, padding=(1, 3)))
    console.print()


def warn_summary(title: str, warnings: list[str]) -> None:
    """Yellow-bordered panel listing warnings."""
    if not warnings:
        return
    body = Text()
    for i, line in enumerate(warnings):
        if i > 0:
            body.append("\n")
        body.append(f"  ! {line}", style="yellow")
    content = Text()
    content.append(f"{title} ({len(warnings)})", style="bold")
    content.append("\n\n")
    content.append(body)
    console.print(Panel(content, border_style="yellow", box=_ROUNDED_BOX, padding=(0, 2)))
    console.print()


@contextmanager
def spin(label: str) -> Iterator[None]:
    """Context manager spinner using Rich status with dots animation."""
    with console.status(label, spinner="dots"):
        yield


@asynccontextmanager
async def spin_timed(label: str) -> AsyncIterator[None]:
    """Async spinner with elapsed-time counter, updated every second.

    Shows e.g. ``⠹ Deploying board (1m 23s)`` and ticks up each second.
    """
    start = time.monotonic()
    stop = asyncio.Event()

    def _elapsed() -> str:
        secs = int(time.monotonic() - start)
        m, s = divmod(secs, 60)
        return f"{m}m {s:02d}s" if m else f"{s}s"

    async def _tick(status: object) -> None:
        while not stop.is_set():
            status.update(f"{label} ({_elapsed()})")  # type: ignore[attr-defined]
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=1.0)

    with console.status(label, spinner="dots") as status:
        task = asyncio.create_task(_tick(status))
        try:
            yield
        finally:
            stop.set()
            await task


def phase_timing(label: str, elapsed_seconds: float) -> None:
    """Dotted leader line: Infrastructure deployed .............. 3m 42s."""
    minutes = int(elapsed_seconds) // 60
    seconds = int(elapsed_seconds) % 60
    time_str = f"{minutes}m {seconds:02d}s" if minutes > 0 else f"{seconds}s"

    # Build a dotted leader to fill the space
    leader_width = max(2, 60 - len(label) - len(time_str) - 2)
    dots = " " + "." * leader_width + " "
    console.print(f"  {label}[dim]{dots}[/dim]{time_str}")


def play_sound() -> None:
    """Fire-and-forget macOS completion sound."""
    if platform.system() == "Darwin":
        import contextlib

        with contextlib.suppress(OSError):
            subprocess.Popen(  # noqa: S603
                ["/usr/bin/afplay", "/System/Library/Sounds/Hero.aiff"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def webhook(url: str, message: str) -> None:
    """POST a message to a webhook URL (fire-and-forget)."""
    try:
        import httpx  # noqa: PLC0415

        with suppress(httpx.HTTPError):
            httpx.post(url, json={"text": message}, timeout=10)
    except ImportError:
        pass


# ── Box styles (import from rich.box) ──

from rich.box import DOUBLE, ROUNDED  # noqa: E402

_DOUBLE_BOX = DOUBLE
_ROUNDED_BOX = ROUNDED

# Re-export for external use
__all__ = [
    "ACCENT",
    "BOARD_ASCII",
    "BOARD_THEME",
    "ascii_banner",
    "banner",
    "completion_box",
    "console",
    "divider",
    "error",
    "header",
    "info",
    "phase_timing",
    "play_sound",
    "spin",
    "spin_timed",
    "step",
    "success",
    "summary_box",
    "warn",
    "warn_summary",
    "webhook",
]
