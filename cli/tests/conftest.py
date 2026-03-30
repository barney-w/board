"""Shared test fixtures."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def surf_manifest_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "surf.project.yaml"


@pytest.fixture
def surf_kit_manifest_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "surf-kit.project.yaml"
