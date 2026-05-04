"""Deployment models — internal dataclasses for deployment state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class DeploymentConfig:
    """Configuration for a board deployment.

    The resource group is the source of truth — it must already exist in Azure
    and the caller must have Contributor or Owner on it. The location comes
    from the RG itself. VM and per-developer resource names are derived from
    the RG name with the leading ``rg-`` stripped.

    Derived properties MUST produce strings identical to extension/src/config.ts.
    """

    developer_name: str
    resource_group: str
    location: str

    @property
    def rg_suffix(self) -> str:
        """RG name with leading 'rg-' stripped, used as a naming prefix."""
        return self.resource_group.removeprefix("rg-")

    @property
    def ssh_host_alias(self) -> str:
        """devvm-{name}"""
        return f"devvm-{self.developer_name}"

    @property
    def hostname(self) -> str:
        """devvm-{name}.{location}.cloudapp.azure.com"""
        return f"devvm-{self.developer_name}.{self.location}.cloudapp.azure.com"

    @property
    def vm_name(self) -> str:
        """vm-{rg-suffix}-{name}"""
        return f"vm-{self.rg_suffix}-{self.developer_name}"

    @property
    def ssh_key_path(self) -> str:
        """~/.ssh/devvm-{name}"""
        return f"~/.ssh/devvm-{self.developer_name}"

    @property
    def ssh_key_path_expanded(self) -> Path:
        """Fully expanded SSH key path."""
        return Path.home() / ".ssh" / f"devvm-{self.developer_name}"

    def tunnel_url(self, explicit_url: str = "") -> str:
        """Get tunnel URL, deriving from name if not explicitly set."""
        if explicit_url:
            return explicit_url
        if self.developer_name:
            return f"https://vscode.dev/tunnel/devvm-{self.developer_name}"
        return ""


@dataclass
class PhaseResult:
    """Result of a single provisioning phase."""

    phase: int
    name: str
    success: bool = True
    elapsed_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class DeploymentResult:
    """Aggregate result of a full deployment."""

    config: DeploymentConfig
    phases: list[PhaseResult] = field(default_factory=list)
    total_elapsed_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return all(p.success for p in self.phases)

    @property
    def all_warnings(self) -> list[str]:
        return [w for p in self.phases for w in p.warnings]

    @property
    def all_errors(self) -> list[str]:
        return [e for p in self.phases for e in p.errors]


@dataclass
class LlmConfig:
    """LLM provider configuration collected during board setup.

    Supports Azure AI Foundry (API key) or direct Anthropic API.
    """

    provider: Literal["foundry", "anthropic", "none"] = "none"
    api_key: str | None = None  # Foundry API key or direct Anthropic key
    endpoint: str | None = None  # Foundry endpoint URL
