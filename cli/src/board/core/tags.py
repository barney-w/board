"""Extra tag loading.

Tags are loaded from board.tags.yaml at the project root. The file is
gitignored so each developer can hold their own tenant-mandated values
without committing them. A board.tags.example.yaml ships as a template.

Schema:

    tags:
      Environment: "dev"
      Owner: "you@example.com"
      CostCenter: "CC-1234"
      ...
"""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

TAGS_FILENAME = "board.tags.yaml"
EXAMPLE_FILENAME = "board.tags.example.yaml"


def find_tags_file() -> Path | None:
    """Locate board.tags.yaml by walking up from cwd."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / TAGS_FILENAME
        if candidate.is_file():
            return candidate
    return None


def find_example_file() -> Path | None:
    """Locate board.tags.example.yaml by walking up from cwd."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / EXAMPLE_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_tags(path: Path | None = None) -> dict[str, str]:
    """Load extra tags from YAML. Returns empty dict if file missing.

    Values are coerced to strings (Azure tags are always strings).
    """
    if path is None:
        path = find_tags_file()
    if path is None or not path.is_file():
        return {}
    yaml = YAML()
    data = yaml.load(path)
    if not data:
        return {}
    raw = data.get("tags", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}
