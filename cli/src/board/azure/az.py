"""Safe async runner for Azure CLI commands with timeouts."""

from __future__ import annotations

import asyncio
import json

from board.core.errors import BoardError


async def az_json(*args: str, timeout: int = 30) -> dict | list:
    """Run an ``az`` CLI command and return parsed JSON output.

    Raises:
        BoardError: On timeout, non-zero exit, or invalid JSON.
    """
    raw = await az_text(*args, timeout=timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"az {args[0]} returned invalid JSON: {exc}"
        raise BoardError(msg) from exc


async def az_text(*args: str, timeout: int = 30) -> str:
    """Run an ``az`` CLI command and return stripped stdout text.

    Raises:
        BoardError: On timeout or non-zero exit.
    """
    proc = await asyncio.create_subprocess_exec(
        "az",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        msg = f"az {args[0]} timed out after {timeout}s"
        raise BoardError(msg) from None

    if proc.returncode != 0:
        detail = stderr.decode().strip() if stderr else "unknown error"
        msg = f"az {args[0]} failed: {detail}"
        raise BoardError(msg)

    return stdout.decode().strip()
