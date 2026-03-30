"""Bundle models — byte-compatible with extension/src/bundle.ts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class BrowserIdeConfig(BaseModel):
    """Browser IDE configuration (v2 bundles)."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    code_server: CodeServerConfig | None = None
    vscode_tunnel: VscodeTunnelConfig | None = None


class CodeServerConfig(BaseModel):
    """code-server credentials."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    password: str = ""
    local_url: str = ""
    ssh_tunnel_command: str = ""


class VscodeTunnelConfig(BaseModel):
    """VS Code Tunnel credentials."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    url: str = ""
    auth: str = ""


# Rebuild BrowserIdeConfig now that forward refs are defined
BrowserIdeConfig.model_rebuild()


class BundlePayload(BaseModel):
    """Decrypted board pass payload.

    Field names MUST match extension/src/bundle.ts BundlePayload interface
    exactly when serialised with model_dump(by_alias=True).
    """

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    developer_name: str
    environment: str
    region: str
    region_short: str
    hostname: str
    username: str
    auth_method: str = "ssh-key"
    ssh_private_key: str
    ssh_public_key: str
    resource_group: str
    vm_name: str
    issued_at: str | None = None
    valid_until: str | None = None
    browser_ide: BrowserIdeConfig | None = Field(None, alias="browserIde")


class BundleEnvelope(BaseModel):
    """Encrypted board pass envelope — JSON on disk.

    Fields MUST match extension/src/bundle.ts BundleEnvelope interface.
    """

    version: int = 2
    format: str = "board-pass"
    salt: str
    iv: str
    ciphertext: str
    tag: str
