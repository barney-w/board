"""Rich console wrapper — themed output functions for Board CLI.

Mirrors the display functions from scripts/lib/ui.sh using Rich panels,
styled text, and spinners instead of gum/ANSI escape codes.

The :class:`Console` class bundles every display helper so that callers can
accept a single ``Console`` object (or ``Console | None``) and call
``console.step(...)``, ``console.success(...)``, etc.  Module-level
convenience functions are also provided for quick one-off use.
"""

from __future__ import annotations

import asyncio
import platform
import subprocess
import time
from contextlib import asynccontextmanager, contextmanager, suppress
from typing import TYPE_CHECKING, Any

from rich.box import DOUBLE, ROUNDED
from rich.console import Console as RichConsole
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

_DOUBLE_BOX = DOUBLE
_ROUNDED_BOX = ROUNDED

# ── ASCII art ──

BOARD_ASCII = (
    "██████╗  ██████╗  █████╗ ██████╗ ██████╗ \n"
    "██╔══██╗██╔═══██╗██╔══██╗██╔══██╗██╔══██╗\n"
    "██████╔╝██║   ██║███████║██████╔╝██║  ██║\n"
    "██╔══██╗██║   ██║██╔══██║██╔══██╗██║  ██║\n"
    "██████╔╝╚██████╔╝██║  ██║██║  ██║██████╔╝\n"
    "╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ "
)


# ── Console class ──


class Console:
    """Themed output helper for Board CLI.

    Wraps a :class:`rich.console.Console` pair (stdout + stderr) and exposes
    every display primitive as an instance method so that a single object can
    be passed around and used for type annotations (``Console | None``).
    """

    def __init__(self) -> None:
        self._out = RichConsole(theme=BOARD_THEME)
        self._err = RichConsole(theme=BOARD_THEME, stderr=True)

    # ── Rich Console pass-through ──

    def print(self, *args: Any, **kwargs: Any) -> None:  # noqa: A003
        """Delegate to the underlying Rich Console's print."""
        self._out.print(*args, **kwargs)

    def input(self, *args: Any, **kwargs: Any) -> str:  # noqa: A003
        """Delegate to the underlying Rich Console's input."""
        return self._out.input(*args, **kwargs)

    def status(self, *args: Any, **kwargs: Any) -> Any:
        """Delegate to the underlying Rich Console's status."""
        return self._out.status(*args, **kwargs)

    # ── Display methods ──

    def header(self, text: str) -> None:
        """Bold accent header text."""
        self._out.print()
        self._out.print(f"[accent]{text}[/accent]")
        self._out.print()

    def banner(self, title: str, tagline: str) -> None:
        """Double-border panel with title and tagline."""
        body = Text()
        body.append(title, style=f"bold {ACCENT}")
        body.append("\n\n")
        body.append(tagline, style="dim")
        self._out.print()
        self._out.print(Panel(body, border_style=ACCENT, box=_DOUBLE_BOX, padding=(1, 3)))
        self._out.print()

    def ascii_banner(self, tagline: str) -> None:
        """ASCII block-letter banner with tagline, inside a double-border panel."""
        body = Text()
        body.append(BOARD_ASCII, style=f"bold {ACCENT}")
        body.append("\n")
        body.append(f"  {tagline}", style="dim")
        self._out.print()
        self._out.print(Panel(body, border_style=ACCENT, box=_DOUBLE_BOX, padding=(1, 3)))
        self._out.print()

    def step(self, current: int, total: int, text: str) -> None:
        """Phase counter: [1/5] Configure."""
        self._out.print(f"[accent]\\[{current}/{total}][/accent] [bold]{text}[/bold]")
        self._out.print()

    def success(self, text: str) -> None:
        """Green checkmark message."""
        self._out.print(f"  [success]✓[/success] {text}")

    def error(self, text: str) -> None:
        """Red cross message (to stderr)."""
        self._err.print(f"  [error]✗[/error] {text}")

    def warn(self, text: str) -> None:
        """Yellow exclamation message."""
        self._out.print(f"  [warn]![/warn] {text}")

    def info(self, text: str) -> None:
        """Dim informational message."""
        self._out.print(f"  [info]{text}[/info]")

    def divider(self) -> None:
        """Horizontal rule."""
        self._out.print(Rule(style="dim"))

    def summary_box(self, title: str, lines: list[str]) -> None:
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
        self._out.print(Panel(content, border_style=ACCENT, box=_ROUNDED_BOX, padding=(0, 2)))
        self._out.print()

    def completion_box(self, title: str, lines: list[str]) -> None:
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
        self._out.print(Panel(content, border_style=ACCENT, box=_DOUBLE_BOX, padding=(1, 3)))
        self._out.print()

    def warn_summary(self, title: str, warnings: list[str]) -> None:
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
        self._out.print(Panel(content, border_style="yellow", box=_ROUNDED_BOX, padding=(0, 2)))
        self._out.print()

    @contextmanager
    def spin(self, label: str) -> Iterator[None]:
        """Context manager spinner using Rich status with dots animation."""
        with self._out.status(label, spinner="dots"):
            yield

    @asynccontextmanager
    async def spin_timed(self, label: str) -> AsyncIterator[None]:
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

        with self._out.status(label, spinner="dots") as status:
            task = asyncio.create_task(_tick(status))
            try:
                yield
            finally:
                stop.set()
                await task

    def phase_timing(self, label: str, elapsed_seconds: float) -> None:
        """Dotted leader line: Infrastructure deployed .............. 3m 42s."""
        minutes = int(elapsed_seconds) // 60
        seconds = int(elapsed_seconds) % 60
        time_str = f"{minutes}m {seconds:02d}s" if minutes > 0 else f"{seconds}s"

        leader_width = max(2, 60 - len(label) - len(time_str) - 2)
        dots = " " + "." * leader_width + " "
        self._out.print(f"  {label}[dim]{dots}[/dim]{time_str}")

    @staticmethod
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

    @staticmethod
    def webhook(url: str, message: str) -> None:
        """POST a message to a webhook URL (fire-and-forget)."""
        try:
            import httpx  # noqa: PLC0415

            with suppress(httpx.HTTPError):
                httpx.post(url, json={"text": message}, timeout=10)
        except ImportError:
            pass


# ── Module-level singleton ──

console: Console = Console()

# ── Module-level convenience functions (delegate to singleton) ──

header = console.header
banner = console.banner
ascii_banner = console.ascii_banner
step = console.step
success = console.success
error = console.error
warn = console.warn
info = console.info
divider = console.divider
summary_box = console.summary_box
completion_box = console.completion_box
warn_summary = console.warn_summary
spin = console.spin
spin_timed = console.spin_timed
phase_timing = console.phase_timing
play_sound = console.play_sound
webhook = console.webhook

# Re-export for external use
__all__ = [
    "ACCENT",
    "BOARD_ASCII",
    "BOARD_THEME",
    "Console",
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
