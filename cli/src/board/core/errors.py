"""Board error hierarchy and retry utility."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


class BoardError(Exception):
    """Base exception for all board errors."""


class PreflightError(BoardError):
    """Prerequisites not met (missing tools, bad config)."""


class DeploymentError(BoardError):
    """Azure deployment failed."""


class SSHError(BoardError):
    """SSH connection or command failed."""


class ManifestError(BoardError):
    """Manifest parsing or validation failed."""


class CryptoError(BoardError):
    """Encryption or decryption failed."""


class ProvisionError(BoardError):
    """Provisioning phase failed."""


async def retry[T](
    fn: Callable[..., Awaitable[T]],
    *args: object,
    max_attempts: int = 3,
    delay: float = 10.0,
    backoff: float = 1.0,
    on_retry: Callable[[int, Exception], Awaitable[None] | None] | None = None,
) -> T:
    """Retry an async function with exponential backoff.

    Args:
        fn: The async function to call.
        *args: Positional arguments to pass to fn.
        max_attempts: Maximum number of attempts (default 3).
        delay: Initial delay between retries in seconds (default 10).
        backoff: Multiplier for delay after each retry (default 1.0 = constant).
        on_retry: Optional callback(attempt, exception) called before each retry.

    Returns:
        The return value of fn.

    Raises:
        The last exception if all attempts fail.
    """
    last_error: Exception | None = None
    current_delay = delay

    for attempt in range(1, max_attempts + 1):
        try:
            return await fn(*args)
        except Exception as e:
            last_error = e
            if attempt == max_attempts:
                break
            if on_retry is not None:
                result = on_retry(attempt, e)
                if asyncio.iscoroutine(result):
                    await result
            await asyncio.sleep(current_delay)
            current_delay *= backoff

    raise last_error  # type: ignore[misc]
