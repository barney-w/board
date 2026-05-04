"""Tests for Pydantic models — validation, rejection, and contract parity."""

from pathlib import Path

from ruamel.yaml import YAML

from board.models.bundle import BundleEnvelope, BundlePayload
from board.models.deployment import DeploymentConfig, PhaseResult
from board.models.manifest import ProjectManifest
from board.models.policies import PoliciesConfig


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

    def test_repo_object_auth(self) -> None:
        manifest = ProjectManifest(
            name="private",
            repo={
                "url": "https://github.com/example/private.git",
                "ref": "feat/private",
                "auth": {
                    "type": "github-token",
                    "keyvault_secret": "github-private-bootstrap-token",
                    "persist": False,
                },
            },
        )

        assert manifest.repo_url == "https://github.com/example/private.git"
        assert manifest.repo_ref == "feat/private"
        assert manifest.repo_auth is not None
        assert manifest.repo_auth.keyvault_secret == "github-private-bootstrap-token"
        assert manifest.repo_auth.persist is False

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
        "region",
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
            region="australiaeast",
            hostname="devvm-jbloggs.australiaeast.cloudapp.azure.com",
            username="devuser",
            ssh_private_key="-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----",
            ssh_public_key="ssh-ed25519 AAAA test",
            resource_group="rg-platform-prod",
            vm_name="vm-platform-prod-jbloggs",
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
            region="australiaeast",
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
            region="r",
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
            "region",
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
    def test_all_derivations_with_rg_prefix(self) -> None:
        cfg = DeploymentConfig(
            developer_name="jbloggs",
            resource_group="rg-platform-prod",
            location="australiaeast",
        )
        assert cfg.rg_suffix == "platform-prod"
        assert cfg.ssh_host_alias == "devvm-jbloggs"
        assert cfg.hostname == "devvm-jbloggs.australiaeast.cloudapp.azure.com"
        assert cfg.vm_name == "vm-platform-prod-jbloggs"
        assert cfg.ssh_key_path == "~/.ssh/devvm-jbloggs"
        assert cfg.tunnel_url() == "https://vscode.dev/tunnel/devvm-jbloggs"
        assert cfg.tunnel_url("https://custom") == "https://custom"

    def test_rg_without_rg_prefix(self) -> None:
        """If the RG name doesn't start with 'rg-', use it as-is."""
        cfg = DeploymentConfig(
            developer_name="jbloggs",
            resource_group="my-team",
            location="australiaeast",
        )
        assert cfg.rg_suffix == "my-team"
        assert cfg.vm_name == "vm-my-team-jbloggs"

    def test_legacy_rg_naming_still_works(self) -> None:
        """The old rg-{env}-{regionShort}-devvm pattern still derives sanely."""
        cfg = DeploymentConfig(
            developer_name="aivm",
            resource_group="rg-dev-aue-devvm",
            location="australiaeast",
        )
        assert cfg.vm_name == "vm-dev-aue-devvm-aivm"


class TestPoliciesConfig:
    def test_security_group_name_default(self) -> None:
        p = PoliciesConfig()
        assert p.security_group_name == "Board VM Users"

    def test_security_group_name_custom(self) -> None:
        p = PoliciesConfig(security_group_name="Corp Dev Team")
        assert p.security_group_name == "Corp Dev Team"

    def test_security_group_name_from_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "board.policies.yaml"
        yaml_file.write_text("require_entra_auth: true\nsecurity_group_name: My Team VMs\n")
        yaml = YAML()
        data = yaml.load(yaml_file)
        p = PoliciesConfig(**data)
        assert p.security_group_name == "My Team VMs"


class TestPhaseResult:
    def test_defaults(self) -> None:
        r = PhaseResult(phase=1, name="validate")
        assert r.success is True
        assert r.warnings == []
        assert r.errors == []
