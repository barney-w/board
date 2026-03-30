"""Assemble a BundlePayload from provisioning outputs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from board.models.bundle import BundlePayload


def build_payload(
    developer_name: str,
    environment: str,
    region: str,
    region_short: str,
    hostname: str,
    username: str,
    auth_method: str,
    ssh_private_key: str,
    ssh_public_key: str,
    resource_group: str,
    vm_name: str,
    tunnel_url: str = "",
    ttl_days: int = 30,
) -> BundlePayload:
    """Build a :class:`BundlePayload` ready for encryption.

    ``issued_at`` is set to now (UTC) and ``valid_until`` to now + *ttl_days*.
    """
    now = datetime.now(UTC)
    issued_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    valid_until = (now + timedelta(days=ttl_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    return BundlePayload(
        developer_name=developer_name,
        environment=environment,
        region=region,
        region_short=region_short,
        hostname=hostname,
        username=username,
        auth_method=auth_method,
        ssh_private_key=ssh_private_key,
        ssh_public_key=ssh_public_key,
        resource_group=resource_group,
        vm_name=vm_name,
        issued_at=issued_at,
        valid_until=valid_until,
        browserIde=None,
    )
