"""Tests for Pydantic models — validation, rejection, and contract parity."""

from pathlib import Path

from ruamel.yaml import YAML

from board.models.bundle import BundleEnvelope, BundlePayload
from board.models.deployment import DeploymentConfig, PhaseResult
from board.models.manifest import ProjectManifest


class TestProjectManifest:
    def test_load_surf(self, surf_manifest_path: Path) -> None:
        yaml = YAML()
        data = yaml.load(surf_manifest_path)
        manifest = ProjectManifest(**data)
        assert manifest.name == "surf"
        assert manifest.description == "AI platform (Python/FastAPI + Postgres)"
        assert manifest.repo == "https://github.com/barney-w/surf"
        assert manifest.requires.tools == ["python3", "uv", "docker", "just"]
        assert manifest.requires.cloud_init is True
        assert len(manifest.install) == 2
        assert manifest.install[0].label == "API dependencies"
        assert manifest.docker is not None
        assert manifest.docker.compose_file == "docker-compose.yml"
        assert len(manifest.docker.containers) == 3
        assert manifest.docker.containers[0].name == "surf-postgres"
        assert manifest.docker.containers[1].name == "surf-langfuse-db"
        assert manifest.docker.containers[2].name == "surf-otel-collector"
        assert len(manifest.post_docker) == 1
        assert manifest.dev is not None
        assert manifest.dev.run == "just dev"
        assert manifest.dev.description == "API with hot reload"
        assert len(manifest.dev.tasks) == 6
        assert len(manifest.services) == 1
        assert manifest.services[0].name == "surf-api"
        assert manifest.services[0].exec_ == (
            "api/.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8090"
        )
        assert manifest.env is not None
        assert len(manifest.env.keyvault_secrets) == 5
        assert manifest.env.hardcoded["POSTGRES_HOST"] == "localhost"
        assert manifest.env.required == ["ANTHROPIC_API_KEY"]
        assert manifest.vscode is not None
        assert len(manifest.vscode.tasks) == 5
        assert len(manifest.vscode.launch) == 1
        assert len(manifest.health) == 3

    def test_load_surf_kit(self, surf_kit_manifest_path: Path) -> None:
        yaml = YAML()
        data = yaml.load(surf_kit_manifest_path)
        manifest = ProjectManifest(**data)
        assert manifest.name == "surf-kit"
        assert manifest.requires.tools == ["node", "pnpm"]
        assert manifest.docker is None
        assert len(manifest.install) == 2
        assert manifest.dev is not None
        assert manifest.dev.run == "pnpm run dev"
        assert manifest.dev.description == "Dev server with hot reload"
        assert manifest.vscode is not None
        assert len(manifest.vscode.tasks) == 4
        assert len(manifest.health) == 2

    def test_project_path_default(self) -> None:
        m = ProjectManifest(name="test-proj")
        assert m.project_path == "~/projects/test-proj"

    def test_project_path_explicit(self) -> None:
        m = ProjectManifest(name="test-proj", path="~/custom/path")
        assert m.project_path == "~/custom/path"

    def test_project_dir_name(self) -> None:
        m = ProjectManifest(name="test-proj", path="~/projects/test-proj")
        assert m.project_dir_name == "test-proj"

    def test_minimal_manifest(self) -> None:
        m = ProjectManifest(name="minimal")
        assert m.name == "minimal"
        assert m.requires.tools == []
        assert m.install == []
        assert m.docker is None
        assert m.services == []


class TestBundlePayload:
    """Field names must match extension/src/bundle.ts BundlePayload interface."""

    EXPECTED_CAMEL_FIELDS = {
        "developerName",
        "environment",
        "region",
        "regionShort",
        "hostname",
        "username",
        "authMethod",
        "sshPrivateKey",
        "sshPublicKey",
        "resourceGroup",
        "vmName",
        "issuedAt",
        "validUntil",
        "browserIde",
    }

    def test_camel_case_serialisation(self) -> None:
        payload = BundlePayload(
            developer_name="jbloggs",
            environment="personal",
            region="australiaeast",
            region_short="aue",
            hostname="devvm-jbloggs.australiaeast.cloudapp.azure.com",
            username="devuser",
            ssh_private_key="-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----",
            ssh_public_key="ssh-ed25519 AAAA test",
            resource_group="rg-personal-aue-devvm",
            vm_name="vm-personal-aue-devvm-jbloggs",
        )
        dumped = payload.model_dump(by_alias=True, exclude_none=True)
        assert set(dumped.keys()) == self.EXPECTED_CAMEL_FIELDS - {
            "issuedAt",
            "validUntil",
            "browserIde",
        }

    def test_all_fields_present(self) -> None:
        payload = BundlePayload(
            developer_name="jbloggs",
            environment="personal",
            region="australiaeast",
            region_short="aue",
            hostname="devvm-jbloggs.australiaeast.cloudapp.azure.com",
            username="devuser",
            ssh_private_key="key",
            ssh_public_key="pub",
            resource_group="rg",
            vm_name="vm",
            issued_at="2026-03-29T00:00:00Z",
            valid_until="2026-04-28T00:00:00Z",
        )
        dumped = payload.model_dump(by_alias=True, exclude_none=True)
        assert "developerName" in dumped
        assert "issuedAt" in dumped
        assert "validUntil" in dumped

    def test_field_names_match_typescript(self) -> None:
        """Verify all camelCase field names match the TypeScript interface."""
        payload = BundlePayload(
            developer_name="x",
            environment="e",
            region="r",
            region_short="rs",
            hostname="h",
            username="u",
            ssh_private_key="k",
            ssh_public_key="p",
            resource_group="rg",
            vm_name="vm",
            issued_at="t",
            valid_until="t",
        )
        dumped = payload.model_dump(by_alias=True, exclude_none=True)
        # These are the exact field names from extension/src/bundle.ts
        for field_name in [
            "developerName",
            "environment",
            "region",
            "regionShort",
            "hostname",
            "username",
            "authMethod",
            "sshPrivateKey",
            "sshPublicKey",
            "resourceGroup",
            "vmName",
            "issuedAt",
            "validUntil",
        ]:
            assert field_name in dumped, f"Missing field: {field_name}"


class TestBundleEnvelope:
    def test_defaults(self) -> None:
        env = BundleEnvelope(salt="s", iv="i", ciphertext="c", tag="t")
        assert env.version == 2
        assert env.format == "board-pass"


class TestDeploymentConfig:
    def test_all_derivations(self) -> None:
        cfg = DeploymentConfig(
            developer_name="jbloggs",
            environment="personal",
            region="australiaeast",
            region_short="aue",
        )
        assert cfg.ssh_host_alias == "devvm-jbloggs"
        assert cfg.hostname == "devvm-jbloggs.australiaeast.cloudapp.azure.com"
        assert cfg.resource_group == "rg-personal-aue-devvm"
        assert cfg.vm_name == "vm-personal-aue-devvm-jbloggs"
        assert cfg.ssh_key_path == "~/.ssh/devvm-jbloggs"
        assert cfg.tunnel_url() == "https://vscode.dev/tunnel/devvm-jbloggs"
        assert cfg.tunnel_url("https://custom") == "https://custom"


class TestPhaseResult:
    def test_defaults(self) -> None:
        r = PhaseResult(phase=1, name="validate")
        assert r.success is True
        assert r.warnings == []
        assert r.errors == []
