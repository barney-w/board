"""Questionary prompt wrappers with non-interactive fallback.

When BOARD_NON_INTERACTIVE is set (1/true/yes), all prompts are skipped
and sensible defaults or BOARD_* env var overrides are returned instead.
"""

from __future__ import annotations

import os
import re

import questionary
from questionary import Choice


def _is_non_interactive() -> bool:
    return os.environ.get("BOARD_NON_INTERACTIVE", "").lower() in ("1", "true", "yes")


async def input_text(prompt: str, default: str = "") -> str:
    """Text input. Non-interactive: return *default*."""
    if _is_non_interactive():
        return default
    result = await questionary.text(prompt, default=default).ask_async()
    if result is None:
        raise KeyboardInterrupt
    return result


async def input_validated(
    prompt: str,
    default: str = "",
    pattern: str = ".*",
    message: str = "Invalid input",
) -> str:
    """Regex-validated text input. Non-interactive: return *default*."""
    if _is_non_interactive():
        return default

    compiled = re.compile(pattern)

    def _validate(text: str) -> bool | str:
        if compiled.match(text):
            return True
        return message

    result = await questionary.text(prompt, default=default, validate=_validate).ask_async()
    if result is None:
        raise KeyboardInterrupt
    return result


async def choose(prompt: str, choices: list[str], default: str = "") -> str:
    """Single-select from a list. Non-interactive: return *default* or BOARD_{key} env var."""
    if _is_non_interactive():
        # Try env var override derived from the prompt (e.g. "Region" -> BOARD_REGION)
        key = _prompt_to_env_key(prompt)
        env_val = os.environ.get(f"BOARD_{key}", "")
        if env_val and env_val in choices:
            return env_val
        return default or (choices[0] if choices else "")

    result = await questionary.select(prompt, choices=choices, default=default or None).ask_async()
    if result is None:
        raise KeyboardInterrupt
    return result


async def checklist(
    prompt: str,
    choices: list[str],
    defaults: list[str] | None = None,
) -> list[str]:
    """Multi-select with pre-checked items. Non-interactive: return BOARD_PROJECTS or *defaults*."""
    if _is_non_interactive():
        env_val = os.environ.get("BOARD_PROJECTS", "")
        if env_val:
            return env_val.split()
        return defaults if defaults is not None else []

    q_choices = [Choice(title=c, checked=(c in (defaults or []))) for c in choices]
    result = await questionary.checkbox(prompt, choices=q_choices).ask_async()
    if result is None:
        raise KeyboardInterrupt
    return result


async def confirm(prompt: str, default: bool = True) -> bool:
    """Yes/no confirmation. Non-interactive: return True."""
    if _is_non_interactive():
        return True
    result = await questionary.confirm(prompt, default=default).ask_async()
    if result is None:
        raise KeyboardInterrupt
    return result


async def secret(prompt: str) -> str:
    """Password input. Non-interactive: return empty string."""
    if _is_non_interactive():
        return ""
    result = await questionary.password(prompt).ask_async()
    if result is None:
        raise KeyboardInterrupt
    return result


def _prompt_to_env_key(prompt: str) -> str:
    """Derive an env var key from a prompt string.

    "Select region" -> "REGION", "Auth method" -> "AUTH_METHOD"
    """
    # Strip punctuation, uppercase, replace spaces with underscores
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", prompt).strip().upper()
    parts = cleaned.split()
    # Drop common leading verbs
    if parts and parts[0] in ("SELECT", "CHOOSE", "PICK", "ENTER"):
        parts = parts[1:]
    return "_".join(parts)


__all__ = [
    "checklist",
    "choose",
    "confirm",
    "input_text",
    "input_validated",
    "secret",
]
