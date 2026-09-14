"""v0.2 spec C — ``--assert-readonly`` tri-state verification (Edward / QA).

Independence note: the engineer's test injects a mutation via ``merge_records``.
These tests inject at a *different* pipeline point
(``apply_usage_and_provenance``) and additionally prove the guard actually
**compares tree state** (a same-size content edit is caught) rather than merely
reading a flag.
"""

from __future__ import annotations

import importlib
import shutil
from pathlib import Path

import pytest

from conftest import REPO_ROOT
from skillgov.cli.main import collect
from skillgov.config import Config
from skillgov.errors import ReadOnlyViolation
from skillgov.logging_setup import NullReporter


def _cli_module():
    return importlib.import_module("skillgov.cli.main")


def _copy_hermes(tmp_path: Path) -> Path:
    dst = tmp_path / "hermes-root"
    shutil.copytree(str(REPO_ROOT / "tests" / "fixtures" / "hermes-root"), str(dst))
    return dst


def _inject_write_at_merge(monkeypatch, target: Path, *, same_size=False):
    """Make the pipeline write into *target* mid-run (independent injection point)."""
    cli = _cli_module()
    original = cli.apply_usage_and_provenance

    def writing(*args, **kwargs):
        victim = target / "skills" / "demo-alpha" / "SKILL.md"
        if same_size and victim.is_file():
            original_bytes = victim.read_bytes()
            victim.write_bytes(original_bytes[::-1] if len(original_bytes) % 2 == 0
                               else original_bytes[:-1] + b"x")
        else:
            (target / "skills" / "injected-mid-run.txt").write_text("x", encoding="utf-8")
        return original(*args, **kwargs)

    monkeypatch.setattr(cli, "apply_usage_and_provenance", writing)


# ------------------------------------------------------------ default off ------
def test_default_off_does_not_snapshot(monkeypatch, tmp_path):
    """When off, ``snapshot_tree`` must not be called at all."""
    cli = _cli_module()

    def boom(*a, **k):  # pragma: no cover - only trips on regression
        raise AssertionError("snapshot_tree called although assert_readonly=False")

    monkeypatch.setattr(cli, "snapshot_tree", boom)
    root = _copy_hermes(tmp_path)
    assert Config().assert_readonly is False
    result = collect(Config(hermes_root=root, out_dir=tmp_path / "out"), NullReporter())
    assert len(result.records) > 0


def test_default_off_tolerates_midrun_write(monkeypatch, tmp_path):
    root = _copy_hermes(tmp_path)
    _inject_write_at_merge(monkeypatch, root)
    result = collect(Config(hermes_root=root, out_dir=tmp_path / "out"), NullReporter())
    assert len(result.records) == 3  # no exception even though a write happened


# ------------------------------------------------------------------- pass ------
def test_on_clean_tree_passes(tmp_path):
    root = _copy_hermes(tmp_path)
    result = collect(
        Config(hermes_root=root, out_dir=tmp_path / "out", assert_readonly=True),
        NullReporter(),
    )
    assert len(result.records) == 3


# ----------------------------------------------------------------- detect ------
def test_on_detects_midrun_write(monkeypatch, tmp_path):
    root = _copy_hermes(tmp_path)
    _inject_write_at_merge(monkeypatch, root)
    with pytest.raises(ReadOnlyViolation):
        collect(Config(hermes_root=root, out_dir=tmp_path / "out",
                       assert_readonly=True), NullReporter())


def test_on_detects_same_size_content_edit(monkeypatch, tmp_path):
    """Proves a real comparison: same file count and byte size, changed mtime."""
    root = _copy_hermes(tmp_path)
    _inject_write_at_merge(monkeypatch, root, same_size=True)
    with pytest.raises(ReadOnlyViolation):
        collect(Config(hermes_root=root, out_dir=tmp_path / "out",
                       assert_readonly=True), NullReporter())


def test_on_exit_code_is_one_via_cli(monkeypatch, tmp_path):
    cli = _cli_module()
    root = _copy_hermes(tmp_path)
    _inject_write_at_merge(monkeypatch, root)
    code = cli.main(["inventory", "--hermes-root", str(root),
                     "--out", str(tmp_path / "out"), "--assert-readonly"])
    assert code == 1
