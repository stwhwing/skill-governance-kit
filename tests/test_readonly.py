"""Tests for the read-only guardrail."""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgov.config import Config
from skillgov.errors import ReadOnlyViolation
from skillgov.logging_setup import NullReporter
from skillgov.readonly import (
    assert_no_writes,
    snapshot_tree,
    snapshots_equal,
    sqlite_ro,
)


def _collect(hermes_root: Path, openclaw_root: Path, out_dir: Path):
    from skillgov.cli.main import collect

    config = Config(
        hermes_root=hermes_root,
        openclaw_root=openclaw_root,
        out_dir=out_dir,
    )
    return collect(config, NullReporter())


def test_sqlite_ro_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sqlite_ro(tmp_path / "nope.db")


def test_sqlite_ro_is_read_only(hermes_root_with_db: Path) -> None:
    import sqlite3

    connection = sqlite_ro(hermes_root_with_db / "skills" / "state.db")
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE should_fail (x INTEGER)")
    finally:
        connection.close()


def test_collect_does_not_write_to_roots(hermes_root, openclaw_root, tmp_path) -> None:
    before_hermes = snapshot_tree(hermes_root)
    before_openclaw = snapshot_tree(openclaw_root)

    _collect(hermes_root, openclaw_root, tmp_path / "out")

    after_hermes = snapshot_tree(hermes_root)
    after_openclaw = snapshot_tree(openclaw_root)

    assert snapshots_equal(before_hermes, after_hermes)
    assert snapshots_equal(before_openclaw, after_openclaw)
    assert_no_writes(before_hermes, after_hermes)
    assert before_hermes.file_count > 0


def test_assert_no_writes_detects_change(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")
    before = snapshot_tree(root)
    (root / "b.txt").write_text("world", encoding="utf-8")
    after = snapshot_tree(root)
    with pytest.raises(ReadOnlyViolation):
        assert_no_writes(before, after)
