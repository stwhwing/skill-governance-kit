"""Tests for the read-only guardrail."""

from __future__ import annotations

import importlib
import shutil
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


# -- --assert-readonly switch (v0.2) -----------------------------------------


def _cli_module():
    """The ``skillgov.cli.main`` *module*.

    ``skillgov.cli`` re-exports a ``main`` *function*, so
    ``import skillgov.cli.main as m`` would bind the function instead of the
    module; ``importlib.import_module`` resolves ``sys.modules`` reliably.
    """
    return importlib.import_module("skillgov.cli.main")


def _copied_root(source: Path, tmp_path: Path, name: str = "hermes-root") -> Path:
    copied = tmp_path / name
    shutil.copytree(str(source), str(copied))
    return copied


def _install_mutation_hook(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    """Make ``merge_records`` write into *target* mid-collection."""
    cli_main = _cli_module()

    original_merge = cli_main.merge_records

    def writing_merge(record_lists):
        (target / "skills" / "injected-during-run.txt").write_text(
            "mutated", encoding="utf-8"
        )
        return original_merge(record_lists)

    monkeypatch.setattr(cli_main, "merge_records", writing_merge)


def test_assert_readonly_default_off(hermes_root, tmp_path, monkeypatch) -> None:
    """Default: no snapshot guard, behaviour identical to v0.1."""
    from skillgov.cli.main import collect

    assert Config().assert_readonly is False
    copied = _copied_root(hermes_root, tmp_path)
    _install_mutation_hook(monkeypatch, copied)
    config = Config(hermes_root=copied, out_dir=tmp_path / "out")
    result = collect(config, NullReporter())  # must not raise
    assert len(result.records) > 0


def test_assert_readonly_passes_on_untouched_roots(
    hermes_root, openclaw_root, tmp_path
) -> None:
    from skillgov.cli.main import collect

    config = Config(
        hermes_root=hermes_root,
        openclaw_root=openclaw_root,
        out_dir=tmp_path / "out",
        assert_readonly=True,
    )
    result = collect(config, NullReporter())
    assert len(result.records) == 5


def test_assert_readonly_detects_midrun_write(
    hermes_root, tmp_path, monkeypatch
) -> None:
    from skillgov.cli.main import collect

    copied = _copied_root(hermes_root, tmp_path)
    _install_mutation_hook(monkeypatch, copied)
    config = Config(hermes_root=copied, out_dir=tmp_path / "out", assert_readonly=True)
    with pytest.raises(ReadOnlyViolation):
        collect(config, NullReporter())


def test_assert_readonly_exit_one_via_cli(
    hermes_root, tmp_path, monkeypatch
) -> None:
    """End to end: a tree mutation under --assert-readonly exits 1."""
    cli_main = _cli_module()

    copied = _copied_root(hermes_root, tmp_path)
    _install_mutation_hook(monkeypatch, copied)
    code = cli_main.main(
        [
            "inventory",
            "--hermes-root",
            str(copied),
            "--out",
            str(tmp_path / "out"),
            "--assert-readonly",
        ]
    )
    assert code == 1
