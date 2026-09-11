"""Unit tests for the Hermes adapter (usage.json + optional state.db)."""

from __future__ import annotations

from pathlib import Path

from skillgov.adapters.hermes import HermesAdapter
from skillgov.logging_setup import NullReporter


def test_discover_finds_three_skills(hermes_root: Path) -> None:
    adapter = HermesAdapter(NullReporter())
    records = adapter.discover(hermes_root)
    ids = {record.skill_id for record in records}
    assert ids == {"hermes:demo-alpha", "hermes:demo-beta", "hermes:archive-demo-old"}
    assert all(record.ecosystem == "hermes" for record in records)


def test_usage_from_usage_json(hermes_root: Path) -> None:
    adapter = HermesAdapter(NullReporter())
    usage = adapter.usage(hermes_root)
    assert usage["demo-alpha"].use_count == 7
    assert usage["demo-alpha"].patch_count == 3
    assert usage["demo-alpha"].last_used_at == "2025-02-01T00:00:00Z"
    assert usage["demo-beta"].use_count == 0
    assert usage["demo-alpha"].evidence_source == "usage_json"
    assert usage["demo-alpha"].confidence == "A"


def test_missing_usage_json_degrades(degenerate_root: Path) -> None:
    reporter = NullReporter()
    adapter = HermesAdapter(reporter)
    usage = adapter.usage(degenerate_root / "hermes-root")
    assert usage == {}
    assert any("missing_usage_json" in warning for warning in reporter.warnings)


def test_state_db_overrides_usage_json(hermes_root_with_db: Path) -> None:
    adapter = HermesAdapter(NullReporter())
    usage = adapter.usage(hermes_root_with_db)
    # state.db holds 2 demo-alpha views, 1 demo-beta view -> authoritative.
    assert usage["demo-alpha"].use_count == 2
    assert usage["demo-alpha"].evidence_source == "state_db"
    assert usage["demo-beta"].use_count == 1
    assert usage["demo-alpha"].last_used_at == "2025-03-02T00:00:00Z"


def test_provenance_from_usage_json(hermes_root: Path) -> None:
    adapter = HermesAdapter(NullReporter())
    provenance = adapter.provenance(hermes_root)
    kinds = {evidence.kind for evidence in provenance["demo-alpha"]}
    assert "curator" in kinds
