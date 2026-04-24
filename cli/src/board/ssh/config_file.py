"""SSH config managed block operations.

Manages ``# BEGIN board: {alias}`` / ``# END board: {alias}`` marker
blocks in ~/.ssh/config. The block format is a contract shared with
extension/src/ssh.ts and MUST remain identical.
"""

from __future__ import annotations

from pathlib import Path

_MARKER_PREFIX = "# BEGIN board:"
_MARKER_SUFFIX = "# END board:"

# Service port forwarding: (local_port, remote_port, label, local_url)
SERVICE_PORTS: list[tuple[int, int, str, str]] = [
    (8080, 8080, "code-server", "http://localhost:8080"),
    (9091, 9190, "Cockpit", "https://localhost:9091"),
    (9444, 9443, "Portainer", "https://localhost:9444"),
]


def _begin_marker(alias: str) -> str:
    return f"{_MARKER_PREFIX} {alias}"


def _end_marker(alias: str) -> str:
    return f"{_MARKER_SUFFIX} {alias}"


def read_managed_block(config_path: Path, alias: str) -> str | None:
    """Read the managed block for a given SSH host alias.

    Args:
        config_path: Path to the SSH config file.
        alias: Host alias (e.g. "devvm-jbloggs").

    Returns:
        The block content (including markers), or None if not found.
    """
    config_path = Path(config_path).expanduser()
    if not config_path.exists():
        return None

    content = config_path.read_text()
    begin = _begin_marker(alias)
    end = _end_marker(alias)

    begin_idx = content.find(begin)
    end_idx = content.find(end)

    if begin_idx == -1 or end_idx == -1:
        return None

    return content[begin_idx : end_idx + len(end)]


def write_managed_block(config_path: Path, alias: str, block: str) -> None:
    """Insert or replace a managed block in SSH config.

    If a block for *alias* already exists, it is replaced. Otherwise
    the block is appended. Creates the file and parent directory if
    they don't exist.

    Args:
        config_path: Path to the SSH config file.
        alias: Host alias (e.g. "devvm-jbloggs").
        block: The SSH config content (Host stanza lines, without markers).
    """
    config_path = Path(config_path).expanduser()
    begin = _begin_marker(alias)
    end = _end_marker(alias)
    managed_block = f"{begin}\n{block}\n{end}"

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    if not config_path.exists():
        config_path.write_text(managed_block + "\n")
        config_path.chmod(0o600)
        return

    content = config_path.read_text()
    begin_idx = content.find(begin)
    end_idx = content.find(end)

    if begin_idx != -1 and end_idx != -1:
        # Replace existing block
        before = content[:begin_idx]
        after = content[end_idx + len(end) :]
        updated = before + managed_block + after
    else:
        # Append new block
        if len(content) == 0:
            updated = managed_block + "\n"
        else:
            separator = "\n" if content.endswith("\n") else "\n\n"
            updated = content + separator + managed_block + "\n"

    config_path.write_text(updated)
    config_path.chmod(0o600)


def remove_managed_block(config_path: Path, alias: str) -> bool:
    """Remove a managed block from SSH config.

    Args:
        config_path: Path to the SSH config file.
        alias: Host alias (e.g. "devvm-jbloggs").

    Returns:
        True if the block was found and removed, False otherwise.
    """
    config_path = Path(config_path).expanduser()
    if not config_path.exists():
        return False

    content = config_path.read_text()
    begin = _begin_marker(alias)
    end = _end_marker(alias)

    begin_idx = content.find(begin)
    end_idx = content.find(end)

    if begin_idx == -1 or end_idx == -1:
        return False

    before = content[:begin_idx]
    after = content[end_idx + len(end) :]

    # Clean up extra blank lines at the junction
    cleaned = (before + after).replace("\n\n\n", "\n\n").strip()
    result = cleaned + "\n" if cleaned else ""

    config_path.write_text(result)
    config_path.chmod(0o600)
    return True


def build_ssh_key_config_block(
    alias: str,
    hostname: str,
    key_path: str,
    username: str = "devuser",
) -> str:
    """Build the SSH config Host stanza for ssh-key authentication.

    The format matches extension/src/ssh.ts buildSshKeyConfigBlock exactly.

    Args:
        alias: Host alias (e.g. "devvm-jbloggs").
        hostname: FQDN or IP of the host.
        key_path: Path to the SSH private key file.
        username: SSH username (default "devuser").

    Returns:
        Multi-line SSH config block (without markers).
    """
    return "\n".join(
        [
            f"Host {alias}",
            f"    HostName {hostname}",
            f"    User {username}",
            f"    IdentityFile {key_path}",
            "    ForwardAgent yes",
            "    ServerAliveInterval 60",
            "    ServerAliveCountMax 3",
            "    StrictHostKeyChecking accept-new",
        ]
    )


def build_entra_id_config_block(
    alias: str,
    hostname: str,
    user: str | None = None,
) -> str:
    """Build SSH config for Entra ID authentication.

    Uses short-lived certificates generated by ``az ssh config``. The certs
    are stored in ``~/.ssh/board-entra/<alias>/`` and refreshed before each
    connection by the extension or CLI.

    Format must match extension/src/ssh.ts buildEntraIdConfigBlock.
    """
    cert_dir = f"~/.ssh/board-entra/{alias}"
    lines = [
        f"Host {alias}",
        f"    HostName {hostname}",
    ]
    if user:
        lines.append(f"    User {user}")
    lines.extend(
        [
            f"    CertificateFile {cert_dir}/id_rsa.pub-aadcert.pub",
            f"    IdentityFile {cert_dir}/id_rsa",
            "    ForwardAgent yes",
            "    ServerAliveInterval 60",
            "    ServerAliveCountMax 3",
        ]
    )
    for local_port, remote_port, _label, _url in SERVICE_PORTS:
        lines.append(f"    LocalForward {local_port} 127.0.0.1:{remote_port}")
    return "\n".join(lines)


def refresh_entra_certs(alias: str, resource_group: str, vm_name: str) -> tuple[bool, str]:
    """Generate/refresh Entra ID SSH certificates via ``az ssh config``.

    Certificates are short-lived (~1 hour). Call before each connection.
    Returns (success, entra_user) where entra_user is the UPN from the cert.
    """
    import re
    import subprocess
    from pathlib import Path

    cert_dir = Path.home() / ".ssh" / "board-entra" / alias
    cert_dir.mkdir(parents=True, exist_ok=True)

    # Remove old key files to avoid interactive "Overwrite?" prompt from az
    for f in ["id_rsa", "id_rsa.pub", "id_rsa.pub-aadcert.pub"]:
        (cert_dir / f).unlink(missing_ok=True)

    tmp_config = cert_dir / "ssh_config"
    result = subprocess.run(
        [
            "az", "ssh", "config",
            "-f", str(tmp_config),
            "--resource-group", resource_group,
            "--name", vm_name,
            "--keys-dest-folder", str(cert_dir),
            "--overwrite",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    entra_user = ""
    if tmp_config.exists():
        match = re.search(r"^\s*User\s+(.+)$", tmp_config.read_text(), re.MULTILINE)
        if match:
            entra_user = match.group(1).strip()
        tmp_config.unlink(missing_ok=True)

    return result.returncode == 0, entra_user
