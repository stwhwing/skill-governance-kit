"""Unit tests for the OpenClaw adapter and the trajectory container split."""

from __future__ import annotations

from pathlib import Path

from skillgov.adapters.openclaw import OpenClawAdapter
from skillgov.adapters.trajectory import (
    iter_trajectory_files,
    parse_trajectory_files,
)
from skillgov.logging_setup import NullReporter


def test_discover_finds_two_skills(openclaw_root: Path) -> None:
    adapter = OpenClawAdapter(NullReporter())
    ids = {record.skill_id for record in adapter.discover(openclaw_root)}
    assert ids == {"openclaw:demo-alpha", "openclaw:demo-gamma"}


def test_strict_usage_counts_only_arguments_path(openclaw_root: Path) -> None:
    adapter = OpenClawAdapter(NullReporter())
    usage = adapter.usage(openclaw_root)
    # Only the two toolCall blocks with arguments.path count.
    assert usage["demo-alpha"].use_count == 1
    assert usage["demo-gamma"].use_count == 1
    assert usage["demo-alpha"].evidence_source == "trajectory"
    # Body-only references never create a strict usage record.
    assert "legacy-ghost" not in usage


def test_snapshot_entries_never_counted(openclaw_root: Path) -> None:
    files = iter_trajectory_files(openclaw_root / "agents")
    result = parse_trajectory_files(files)
    assert "legacy-ghost" in result.snapshot_names
    assert "legacy-ghost" not in result.strict_use
    assert "demo-gamma" in result.mentions  # corroboration captured separately
    assert result.strict_use == {"demo-alpha": 1, "demo-gamma": 1}


def test_bad_jsonl_degrades(degenerate_root: Path) -> None:
    reporter = NullReporter()
    adapter = OpenClawAdapter(reporter)
    usage = adapter.usage(degenerate_root / "openclaw-root")
    # The first (valid) line is still counted despite the malformed ones.
    assert usage["demo-alpha"].use_count == 1
    assert any("bad_jsonl" in warning for warning in reporter.warnings)


def test_empty_skills_dir_degrades(degenerate_root: Path) -> None:
    reporter = NullReporter()
    adapter = OpenClawAdapter(reporter)
    records = adapter.discover(degenerate_root / "openclaw-root")
    assert records == []
    assert any("empty_dir" in warning for warning in reporter.warnings)


def test_store_lock_provenance(openclaw_root: Path) -> None:
    adapter = OpenClawAdapter(NullReporter())
    provenance = adapter.provenance(openclaw_root)
    kinds = {evidence.kind for evidence in provenance["demo-alpha"]}
    assert "store_lock" in kinds
    kinds_gamma = {evidence.kind for evidence in provenance["demo-gamma"]}
    assert "trajectory_mention" in kinds_gamma


def test_max_bytes_truncation_warns(openclaw_root: Path) -> None:
    reporter = NullReporter()
    adapter = OpenClawAdapter(reporter, max_bytes=10)
    adapter.usage(openclaw_root)
    assert any("truncated_input" in warning for warning in reporter.warnings)
