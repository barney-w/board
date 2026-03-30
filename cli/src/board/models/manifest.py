"""Project manifest Pydantic model — the .project.yaml schema."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Requires(BaseModel):
    """System requirements validated before provisioning."""

    tools: list[str] = []
    cloud_init: bool = False


class InstallStep(BaseModel):
    """A labelled idempotent install command."""

    label: str
    run: str


class DockerContainer(BaseModel):
    """A container in the docker compose stack."""

    name: str
    restart_policy: str = "unless-stopped"
    health_cmd: str | None = None
    health_interval: int = 2
    health_timeout: int = 60


class DockerConfig(BaseModel):
    """Docker compose configuration."""

    compose_file: str = "docker-compose.yml"
    containers: list[DockerContainer] = []


class Service(BaseModel):
    """A long-running systemd user service.

    Note: 'exec' is a Python keyword, so we alias exec_ -> exec for YAML.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str = ""
    exec_: str = Field("", alias="exec")
    working_dir: str = ""
    env_file: str = ""
    extra_path: str = ""
    health_url: str = ""
    health_timeout: int = 30


class EnvConfig(BaseModel):
    """Environment variable configuration."""

    file: str = ".env"
    fallback: str = ""
    keyvault_secrets: dict[str, str] = {}
    hardcoded: dict[str, str] = {}
    required: list[str] = []


class PortConfig(BaseModel):
    """VS Code port forwarding configuration."""

    label: str = ""
    auto_forward: Literal["notify", "silent", "ignore"] = "notify"


class VscodeTask(BaseModel):
    """VS Code task definition."""

    label: str
    command: str
    group: str = ""
    background: bool = False


class VscodeLaunch(BaseModel):
    """VS Code launch configuration."""

    name: str
    type: str = "debugpy"
    request: str = "launch"
    module: str = ""
    args: list[str] = []
    cwd: str = ""
    env_file: str = ""
    pre_launch_task: str = ""


class VscodeConfig(BaseModel):
    """VS Code integration configuration."""

    ports: dict[str, PortConfig] = {}
    tasks: list[VscodeTask] = []
    launch: list[VscodeLaunch] = []
    settings: dict[str, str] = {}


class WorkspaceService(BaseModel):
    """A terminal pane service for the workspace."""

    name: str
    command: str


class WorkspaceConfig(BaseModel):
    """Workspace pane configuration."""

    services: list[WorkspaceService] = []


class HealthCheck(BaseModel):
    """A health check definition."""

    label: str
    check: str
    port: int | None = None


class ProjectManifest(BaseModel):
    """Complete .project.yaml schema.

    This is the user-facing contract for declaring project environments.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str = ""
    repo: str = ""
    path: str = ""

    requires: Requires = Requires()
    install: list[InstallStep] = []
    docker: DockerConfig | None = None
    post_docker: list[InstallStep] = []
    services: list[Service] = []
    env: EnvConfig | None = None
    vscode: VscodeConfig | None = None
    workspace: WorkspaceConfig | None = None
    health: list[HealthCheck] = []

    @property
    def project_path(self) -> str:
        """Resolve the project path, defaulting to ~/projects/<name>."""
        return self.path or f"~/projects/{self.name}"

    @property
    def project_dir_name(self) -> str:
        """The directory name component of the project path."""
        return PurePosixPath(self.project_path).name
