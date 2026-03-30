"""SSH key generation — ed25519 keypairs for VM authentication."""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncssh

from board.core.errors import CryptoError


async def generate_keypair(key_path: Path) -> tuple[str, str]:
    """Generate an ed25519 SSH keypair and write to disk.

    Creates both the private key at *key_path* and the public key at
    *key_path*.pub. Sets appropriate file permissions (0600/0644).

    If asyncssh key generation fails (e.g. missing native crypto), falls
    back to ``ssh-keygen -t ed25519``.

    Args:
        key_path: Path for the private key file (public key will be
            at key_path.with_suffix('.pub')).

    Returns:
        Tuple of (private_key_string, public_key_string).

    Raises:
        CryptoError: If key generation fails via both methods.
    """
    key_path = Path(key_path).expanduser()
    pub_path = key_path.with_suffix(".pub")

    # Ensure parent directory exists with safe permissions
    key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    try:
        return await _generate_with_asyncssh(key_path, pub_path)
    except Exception:
        pass

    try:
        return await _generate_with_ssh_keygen(key_path, pub_path)
    except Exception as exc:
        msg = f"SSH key generation failed: {exc}"
        raise CryptoError(msg) from exc


async def _generate_with_asyncssh(
    key_path: Path,
    pub_path: Path,
) -> tuple[str, str]:
    """Generate keypair using asyncssh's native crypto."""
    key = asyncssh.generate_private_key("ssh-ed25519")

    private_pem = key.export_private_key("openssh").decode()
    public_str = key.export_public_key("openssh").decode().strip()

    # Write files with correct permissions
    key_path.write_text(private_pem)
    key_path.chmod(0o600)

    pub_path.write_text(public_str + "\n")
    pub_path.chmod(0o644)

    return private_pem, public_str


async def _generate_with_ssh_keygen(
    key_path: Path,
    pub_path: Path,
) -> tuple[str, str]:
    """Fallback: generate keypair using ssh-keygen CLI."""
    # Remove existing files so ssh-keygen doesn't prompt for overwrite
    key_path.unlink(missing_ok=True)
    pub_path.unlink(missing_ok=True)

    proc = await asyncio.create_subprocess_exec(
        "ssh-keygen",
        "-t",
        "ed25519",
        "-N",
        "",
        "-f",
        str(key_path),
        "-q",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        detail = stderr.decode().strip()
        msg = f"ssh-keygen failed: {detail}"
        raise CryptoError(msg)

    private_str = key_path.read_text()
    public_str = pub_path.read_text().strip()

    # Ensure correct permissions (ssh-keygen usually sets these, but be safe)
    key_path.chmod(0o600)
    pub_path.chmod(0o644)

    return private_str, public_str
