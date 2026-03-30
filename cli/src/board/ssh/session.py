"""SSH session wrapper around asyncssh with Board connection defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import asyncssh

from board.core.errors import SSHError


class SSHSession:
    """Async SSH session with Board's connection defaults.

    Connection options match the bash scripts: no host-key checking,
    10-second connect timeout, 60-second keepalive interval.

    Usage::

        async with SSHSession() as ssh:
            await ssh.connect("devvm-jbloggs.australiaeast.cloudapp.azure.com")
            result = await ssh.run("uname -a")
            print(result.stdout)
    """

    def __init__(self) -> None:
        self._conn: asyncssh.SSHClientConnection | None = None

    async def connect(
        self,
        hostname: str,
        username: str = "devuser",
        key_path: str | Path | None = None,
    ) -> None:
        """Open an SSH connection.

        Args:
            hostname: Remote hostname or IP.
            username: SSH username (default "devuser").
            key_path: Path to private key file. If None, uses SSH agent.

        Raises:
            SSHError: If connection fails.
        """
        connect_kwargs: dict[str, Any] = {
            "host": hostname,
            "username": username,
            "known_hosts": None,
            "connect_timeout": 10,
            "keepalive_interval": 60,
        }
        if key_path is not None:
            resolved = Path(key_path).expanduser()
            connect_kwargs["client_keys"] = [str(resolved)]

        try:
            self._conn = await asyncssh.connect(**connect_kwargs)
        except (OSError, asyncssh.Error) as exc:
            msg = f"SSH connection to {username}@{hostname} failed: {exc}"
            raise SSHError(msg) from exc

    async def run(
        self,
        command: str,
        check: bool = True,
    ) -> asyncssh.SSHCompletedProcess:
        """Run a command on the remote host.

        Args:
            command: Shell command to execute.
            check: If True, raise SSHError on non-zero exit code.

        Returns:
            The completed process result with stdout, stderr, returncode.

        Raises:
            SSHError: If check=True and the command exits non-zero, or
                if no connection is open.
        """
        if self._conn is None:
            msg = "Not connected. Call connect() first."
            raise SSHError(msg)

        try:
            result = await self._conn.run(command, check=check)
        except asyncssh.ProcessError as exc:
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            msg = f"Command failed (exit {exc.exit_status}): {stderr}"
            raise SSHError(msg) from exc
        except asyncssh.Error as exc:
            msg = f"SSH command error: {exc}"
            raise SSHError(msg) from exc
        return result

    async def upload(
        self,
        local_path: str | Path,
        remote_path: str,
    ) -> None:
        """Upload a file via SFTP.

        Args:
            local_path: Local file path.
            remote_path: Destination path on remote.

        Raises:
            SSHError: If the transfer fails or no connection is open.
        """
        if self._conn is None:
            msg = "Not connected. Call connect() first."
            raise SSHError(msg)

        try:
            await asyncssh.scp(str(local_path), (self._conn, remote_path))
        except (OSError, asyncssh.Error) as exc:
            msg = f"Upload failed ({local_path} -> {remote_path}): {exc}"
            raise SSHError(msg) from exc

    async def download(
        self,
        remote_path: str,
        local_path: str | Path,
    ) -> None:
        """Download a file via SFTP.

        Args:
            remote_path: Source path on remote.
            local_path: Local destination path.

        Raises:
            SSHError: If the transfer fails or no connection is open.
        """
        if self._conn is None:
            msg = "Not connected. Call connect() first."
            raise SSHError(msg)

        try:
            await asyncssh.scp((self._conn, remote_path), str(local_path))
        except (OSError, asyncssh.Error) as exc:
            msg = f"Download failed ({remote_path} -> {local_path}): {exc}"
            raise SSHError(msg) from exc

    async def close(self) -> None:
        """Close the SSH connection."""
        if self._conn is not None:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None

    async def __aenter__(self) -> SSHSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()
