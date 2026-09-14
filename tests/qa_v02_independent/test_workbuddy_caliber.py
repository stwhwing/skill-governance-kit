"""v0.2 spec A — WorkBuddy adapter caliber verification (Edward / QA).

My own fixture (``wb_root`` from this package's conftest) exercises every case in
the spec: the ``recentDates`` day-based caliber, orphan ledger keys,
``type != skill`` entries, ``*.bak-*`` / ``_*`` exclusion, ``.archive`` marking,
and the explicit out-of-scope trees (``audit-log``, ``plugins/cache``,
``connectors``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import run_cli
from skillgov.adapters.workbuddy import WorkBuddyAdapter
from skillgov.cli.main import main
from skillgov.logging_setup import NullReporter


def _adapter() -> tuple[WorkBuddyAdapter, NullReporter]:
    rep = NullReporter()
    return WorkBuddyAdapter(rep), rep


# ------------------------------------------------------------- discovery -------
def test_discovery_excludes_backups_underscore_and_out_of_scope_trees(wb_root):
    adapter, _ = _adapter()
    ids = {r.skill_id for r in adapter.discover(wb_root)}
    assert ids == {"workbuddy:wb-a", "workbuddy:wb-b", "workbuddy:archive-wb-d"}, ids
    # *.bak-* , _* , audit-log/, plugins/cache/, connectors/ must all be absent
    for bad in ("wb-c", "wb-e", "pc-skill", "conn-skill"):
        assert not any(bad in sid for sid in ids), bad


def test_archive_dir_marks_presence_archived(wb_root):
    adapter, _ = _adapter()
    by_id = {r.skill_id: r for r in adapter.discover(wb_root)}
    assert by_id["workbuddy:archive-wb-d"].presence == "archived"
    assert by_id["workbuddy:wb-a"].presence == "active"


# --------------------------------------------------------------- usage ---------
def test_usage_caliber_day_based_and_zero_view_patch(wb_root):
    adapter, _ = _adapter()
    usage = adapter.usage(wb_root)
    a = usage["WB-A"]
    assert a.use_count == 3                       # len(recentDates), i.e. DAYS
    assert a.view_count == 0 and a.patch_count == 0
    assert a.last_used_at == "2025-04-05T00:00:00Z"
    assert a.evidence_source == "usage_log"
    assert a.confidence == "A"
    b = usage["WB-B"]                             # empty recentDates, null lastUsed
    assert (b.use_count, b.last_used_at) == (0, None)
    assert b.evidence_source == "usage_log" and b.confidence == "A"


def test_orphan_ledger_entry_warns_and_creates_no_record(wb_root):
    adapter, rep = _adapter()
    usage = adapter.usage(wb_root)
    assert "WB-ORPHAN" not in usage
    orphan = [w for w in rep.warnings if "orphan_ledger_entry" in w]
    assert any("WB-ORPHAN" in w for w in orphan)
    assert len(orphan) == 1, rep.warnings            # exactly one warning


def test_non_skill_ledger_type_is_ignored(wb_root):
    adapter, _ = _adapter()
    # WB-MCP has type "mcp": it must never become a usage record.
    assert "WB-MCP" not in adapter.usage(wb_root)


def test_ledger_present_but_skill_absent_from_tree_produces_no_skill_record(wb_root):
    adapter, _ = _adapter()
    ids = {r.skill_id for r in adapter.discover(wb_root)}
    assert not any("orphan" in sid for sid in ids)


# --------------------------------------------- ledger degrade matrix -----------
@pytest.mark.parametrize(
    "payload, marker",
    [
        (None, "missing_usage_json"),
        ("{}", "empty_usage_log"),
        ("{ not json", "bad_json"),
        ('{"skills": ["a", "b"]}', "bad_json"),
    ],
)
def test_ledger_degrade_matrix(tmp_path, payload, marker):
    write = tmp_path / "skills" / "S1"
    write.mkdir(parents=True)
    (write / "SKILL.md").write_text("---\nname: S1\n---\n\nb\n", encoding="utf-8")
    if payload is not None:
        (tmp_path / "usage-log.json").write_text(payload, encoding="utf-8")
    adapter, rep = _adapter()
    assert adapter.usage(tmp_path) == {}
    assert any(marker in w for w in rep.warnings), rep.warnings


def test_missing_lastuseddate_with_recentdates_gives_null_last_used(tmp_path):
    write = tmp_path / "skills" / "S1"
    write.mkdir(parents=True)
    (write / "SKILL.md").write_text("---\nname: S1\n---\n\nb\n", encoding="utf-8")
    (tmp_path / "usage-log.json").write_text(json.dumps({"skills": {
        "S1": {"type": "skill", "recentDates": ["2025-04-02", "2025-04-03"]}}}),
        encoding="utf-8")
    adapter, _ = _adapter()
    u = adapter.usage(tmp_path)["S1"]
    assert u.use_count == 2 and u.last_used_at is None


def test_illegal_date_strings_are_counted_verbatim(tmp_path):
    """Documented caliber: use_count == len(recentDates) with no validation."""
    write = tmp_path / "skills" / "S1"
    write.mkdir(parents=True)
    (write / "SKILL.md").write_text("---\nname: S1\n---\n\nb\n", encoding="utf-8")
    (tmp_path / "usage-log.json").write_text(json.dumps({"skills": {
        "S1": {"type": "skill", "recentDates": ["2025-04-02", "not-a-date", ""]}}}),
        encoding="utf-8")
    adapter, _ = _adapter()
    assert adapter.usage(tmp_path)["S1"].use_count == 3


def test_empty_skills_dir_degrades_and_all_ledger_keys_orphaned(tmp_path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "usage-log.json").write_text(json.dumps({"skills": {
        "GHOST": {"type": "skill", "recentDates": ["2025-04-02"]}}}), encoding="utf-8")
    adapter, rep = _adapter()
    assert adapter.discover(tmp_path) == []
    assert any("empty_dir" in w for w in rep.warnings)


# ----------------------------------------------------- provenance ---------------
def test_provenance_attaches_usage_log_evidence_for_real_skill(wb_root):
    adapter, _ = _adapter()
    pv = adapter.provenance(wb_root)
    ev = pv["WB-A"]
    assert len(ev) == 1
    assert ev[0].kind == "usage_log" and ev[0].observed_at == "2025-04-05"


def test_provenance_does_not_leak_non_skill_or_orphan_into_records(wb_root):
    """Provenance may scan the whole ledger, but records/reports must not be
    affected by ``type != skill`` or orphan keys."""
    adapter, _ = _adapter()
    rec_ids = {r.skill_id for r in adapter.discover(wb_root)}
    assert not any("mcp" in s or "orphan" in s for s in rec_ids)


# ------------------------------------------------------------- CLI surface -----
def test_cli_reports_workbuddy_section_when_root_given(wb_root, tmp_path):
    out = tmp_path / "out"
    code = main(["inventory", "--workbuddy-root", str(wb_root), "--out", str(out),
                 "--format", "json"])
    assert code == 0
    doc = json.loads((out / "inventory.json").read_text(encoding="utf-8"))
    assert doc["summary"].get("workbuddy") == 3
    ids = [row[0] for row in doc["sections"][0]["rows"]]
    assert ids == ["workbuddy:archive-wb-d", "workbuddy:wb-a", "workbuddy:wb-b"]


def test_cli_missing_workbuddy_root_is_no_source(tmp_path):
    missing = tmp_path / "nope"
    out = tmp_path / "out"
    proc = run_cli(["inventory", "--workbuddy-root", str(missing), "--out", str(out)],
                   tmp_path)
    assert proc.returncode == 3, (proc.returncode, proc.stderr)


def test_cli_workbuddy_root_pointing_at_file_is_no_source(tmp_path):
    afile = tmp_path / "afile"
    afile.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    proc = run_cli(["inventory", "--workbuddy-root", str(afile), "--out", str(out)],
                   tmp_path)
    assert proc.returncode == 3, (proc.returncode, proc.stderr)


def test_cli_workbuddy_missing_skills_dir_degrades_but_keeps_other_sources(
        v01_roots, tmp_path):
    hroot, _ = v01_roots
    wb = tmp_path / "wb-empty"
    wb.mkdir()
    out = tmp_path / "out"
    proc = run_cli(["inventory", "--hermes-root", str(hroot),
                    "--workbuddy-root", str(wb), "--out", str(out)], tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "missing_skills_dir" in proc.stderr and "workbuddy" in proc.stderr
