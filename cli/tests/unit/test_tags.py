"""Tests for board.core.tags — extra tag loading."""

from __future__ import annotations

from typing import TYPE_CHECKING

from board.core import tags as tag_loader

if TYPE_CHECKING:
    from pathlib import Path


def test_load_tags_returns_empty_when_path_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    assert tag_loader.load_tags(missing) == {}


def test_load_tags_returns_empty_when_file_empty(tmp_path: Path) -> None:
    p = tmp_path / "board.tags.yaml"
    p.write_text("")
    assert tag_loader.load_tags(p) == {}


def test_load_tags_returns_empty_when_no_tags_key(tmp_path: Path) -> None:
    p = tmp_path / "board.tags.yaml"
    p.write_text("other: value\n")
    assert tag_loader.load_tags(p) == {}


def test_load_tags_parses_string_values(tmp_path: Path) -> None:
    p = tmp_path / "board.tags.yaml"
    p.write_text('tags:\n  Owner: "you@example.com"\n  CostCenter: "CC-1234"\n  Project: "board"\n')
    result = tag_loader.load_tags(p)
    assert result == {
        "Owner": "you@example.com",
        "CostCenter": "CC-1234",
        "Project": "board",
    }


def test_load_tags_coerces_non_string_values_to_strings(tmp_path: Path) -> None:
    p = tmp_path / "board.tags.yaml"
    # Unquoted YAML values can come back as int/bool — Azure tags must be strings.
    p.write_text("tags:\n  CostCenter: 1234\n  Active: true\n")
    result = tag_loader.load_tags(p)
    assert result == {"CostCenter": "1234", "Active": "True"}


def test_load_tags_ignores_malformed_tags_block(tmp_path: Path) -> None:
    p = tmp_path / "board.tags.yaml"
    p.write_text("tags:\n  - just\n  - a\n  - list\n")
    assert tag_loader.load_tags(p) == {}


def test_find_tags_file_walks_up(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    sub = root / "deep" / "nested"
    sub.mkdir(parents=True)
    (root / tag_loader.TAGS_FILENAME).write_text("tags: {}\n")
    monkeypatch.chdir(sub)
    found = tag_loader.find_tags_file()
    assert found is not None
    assert found.name == tag_loader.TAGS_FILENAME


def test_find_tags_file_returns_none_when_absent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert tag_loader.find_tags_file() is None


def test_find_example_file_walks_up(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    sub = root / "deep"
    sub.mkdir(parents=True)
    (root / tag_loader.EXAMPLE_FILENAME).write_text("tags: {}\n")
    monkeypatch.chdir(sub)
    found = tag_loader.find_example_file()
    assert found is not None
    assert found.name == tag_loader.EXAMPLE_FILENAME
