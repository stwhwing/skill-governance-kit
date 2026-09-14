"""Unit tests for the WorkBuddy adapter (usage-log.json ledger caliber)."""

from __future__ import annotations

import json
from pathlib import Path

from skillgov.adapters.workbuddy import WorkBuddyAdapter
from skillgov.logging_setup import NullReporter


def test_discover_finds_visible_skills(workbuddy_root: Path) -> None:
    adapter = WorkBuddyAdapter(NullReporter())
    records = adapter.discover(workbuddy_root)
    ids = {record.skill_id for record in records}
    # wb-demo + wb-idle are active; .archive/wb-old is archived; the
    # ``*.bak-*`` backup directory and ``_*`` auxiliary files are excluded.
    assert ids == {
        "workbuddy:wb-demo",
        "workbuddy:wb-idle",
        "workbuddy:archive-wb-old",
    }
    assert all(record.ecosystem == "workbuddy" for record in records)
    presence = {record.skill_id: record.presence for record in records}
    assert presence["workbuddy:wb-demo"] == "active"
    assert presence["workbuddy:archive-wb-old"] == "archived"


def test_usage_ledger_caliber(workbuddy_root: Path) -> None:
    adapter = WorkBuddyAdapter(NullReporter())
    usage = adapter.usage(workbuddy_root)
    # wb-orphan is in the ledger but not in the tree -> no record at all.
    assert set(usage) == {"wb-demo", "wb-idle"}
    demo = usage["wb-demo"]
    # use_count counts usage DAYS (recentDates), not invocation times.
    assert demo.use_count == 3
    assert demo.view_count == 0
    assert demo.patch_count == 0
    assert demo.last_used_at == "2025-04-05T00:00:00Z"
    assert demo.evidence_source == "usage_log"
    assert demo.confidence == "A"
    idle = usage["wb-idle"]
    assert idle.use_count == 0
    assert idle.last_used_at is None


def test_usage_warns_for_orphan_ledger_entries(workbuddy_root: Path) -> None:
    reporter = NullReporter()
    adapter = WorkBuddyAdapter(reporter)
    usage = adapter.usage(workbuddy_root)
    assert "wb-orphan" not in usage
    assert any(
        "orphan_ledger_entry" in warning and "wb-orphan" in warning
        for warning in reporter.warnings
    )


def test_last_used_at_uses_date_at_midnight_utc(workbuddy_root: Path) -> None:
    adapter = WorkBuddyAdapter(NullReporter())
    usage = adapter.usage(workbuddy_root)
    assert usage["wb-demo"].last_used_at == "2025-04-05T00:00:00Z"
    assert usage["wb-demo"].last_used_at.endswith("T00:00:00Z")


def test_provenance_from_usage_log(workbuddy_root: Path) -> None:
    adapter = WorkBuddyAdapter(NullReporter())
    provenance = adapter.provenance(workbuddy_root)
    evidence = provenance["wb-demo"]
    assert len(evidence) == 1
    assert evidence[0].kind == "usage_log"
    assert "usage-log.json" in evidence[0].detail
    assert evidence[0].observed_at == "2025-04-05"


def test_missing_usage_log_degrades(tmp_path: Path) -> None:
    reporter = NullReporter()
    adapter = WorkBuddyAdapter(reporter)
    usage = adapter.usage(tmp_path)
    assert usage == {}
    assert any(
        "missing_usage_json" in warning for warning in reporter.warnings
    )


def test_empty_usage_log_degrades(tmp_path: Path) -> None:
    (tmp_path / "usage-log.json").write_text(
        json.dumps({"version": 1, "skills": {}}), encoding="utf-8"
    )
    reporter = NullReporter()
    adapter = WorkBuddyAdapter(reporter)
    usage = adapter.usage(tmp_path)
    assert usage == {}
    assert any("empty_usage_log" in warning for warning in reporter.warnings)


def test_missing_skills_dir_degrades(tmp_path: Path) -> None:
    reporter = NullReporter()
    adapter = WorkBuddyAdapter(reporter)
    assert adapter.discover(tmp_path) == []
    assert any(
        "missing_skills_dir" in warning for warning in reporter.warnings
    )
