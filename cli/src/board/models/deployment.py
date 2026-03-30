"""Deployment models — internal dataclasses for deployment state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DeploymentConfig:
    """Configuration for a board deployment.

    Derived properties MUST produce strings identical to extension/src/config.ts.
    """

    developer_name: str
    environment: str
    region: str
    region_short: str

    @property
    def ssh_host_alias(self) -> str:
        """devvm-{name}"""
        return f"devvm-{self.developer_name}"

    @property
    def hostname(self) -> str:
        """devvm-{name}.{region}.cloudapp.azure.com"""
        return f"devvm-{self.developer_name}.{self.region}.cloudapp.azure.com"

    @property
    def resource_group(self) -> str:
        """rg-{env}-{regionShort}-devvm"""
        return f"rg-{self.environment}-{self.region_short}-devvm"

    @property
    def vm_name(self) -> str:
        """vm-{env}-{regionShort}-devvm-{name}"""
        return f"vm-{self.environment}-{self.region_short}-devvm-{self.developer_name}"

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
