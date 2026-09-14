"""Regression tests for the v0.2 fix round routed by QA (S1 + S4-1..S4-3).

* **S1** — the WorkBuddy caliber footer line must be *conditional*: a run that
  does not include WorkBuddy stays byte-identical to v0.1 (five footer lines).
* **S4-1** — ``provenance()`` must reuse ``usage()``'s filtered ledger mapping,
  so ``type != "skill"`` entries and orphan keys never attach evidence to a
  skill whose usage stays ``none``.
* **S4-2** — archive / exclusion rules are matched per *path segment*, not as
  raw substrings of the whole relative path (all three adapters unified).
* **S4-3** — ``examples/out/**`` is regenerated from the current code and
  therefore matches a fresh run (including ``records.json``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillgov.adapters.fs_scan import ARCHIVE_MARKERS, path_is_archived, scan_skills
from skillgov.adapters.hermes import HermesAdapter
from skillgov.adapters.openclaw import OpenClawAdapter
from skillgov.adapters.workbuddy import WorkBuddyAdapter
from skillgov.cli.main import main
from skillgov.logging_setup import NullReporter
from skillgov.report.render import (
    CALIBER_FOOTER,
    WORKBUDDY_CALIBER_LINE,
    caliber_footer,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWS = ("inventory", "usage", "mirror", "report")
V01_FOOTER_LINES = 5


def _write_skill(dir_path: Path, name: str) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: demo\nversion: 1.0.0\n---\n\n# body\n",
        encoding="utf-8",
    )


# ------------------------------------------------------------------- S1 -------
def test_footer_constant_is_exactly_the_v01_five_lines() -> None:
    assert len(CALIBER_FOOTER) == V01_FOOTER_LINES
    assert not any("WorkBuddy" in line for line in CALIBER_FOOTER)
    assert caliber_footer(False) == CALIBER_FOOTER
    assert caliber_footer(True) == CALIBER_FOOTER + (WORKBUDDY_CALIBER_LINE,)


def test_no_workbuddy_run_footer_is_five_lines_and_output_has_no_workbuddy(
    hermes_root, openclaw_root, tmp_path
) -> None:
    out = tmp_path / "out"
    assert (
        main(
            [
                "report",
                "--hermes-root", str(hermes_root),
                "--openclaw-root", str(openclaw_root),
                "--since", "2025-01-01",
                "--out", str(out),
                "--format", "md,json",
            ]
        )
        == 0
    )

    for view in VIEWS:
        doc = json.loads((out / f"{view}.json").read_text(encoding="utf-8"))
        assert tuple(doc["footer"]) == CALIBER_FOOTER, view
        assert len(doc["footer"]) == V01_FOOTER_LINES, view

    blob = "\n".join(
        (out / f"{view}.{ext}").read_text(encoding="utf-8")
        for view in VIEWS
        for ext in ("md", "json")
    )
    blob += (out / "records.json").read_text(encoding="utf-8")
    assert "workbuddy" not in blob.lower()


def test_workbuddy_run_appends_exactly_one_caliber_line(
    hermes_root, openclaw_root, workbuddy_root, tmp_path
) -> None:
    out = tmp_path / "out"
    assert (
        main(
            [
                "report",
                "--hermes-root", str(hermes_root),
                "--openclaw-root", str(openclaw_root),
                "--workbuddy-root", str(workbuddy_root),
                "--out", str(out),
                "--format", "md,json",
            ]
        )
        == 0
    )
    for view in VIEWS:
        doc = json.loads((out / f"{view}.json").read_text(encoding="utf-8"))
        assert len(doc["footer"]) == V01_FOOTER_LINES + 1, view
        assert tuple(doc["footer"][:V01_FOOTER_LINES]) == CALIBER_FOOTER, view
        assert doc["footer"][-1] == WORKBUDDY_CALIBER_LINE, view
        md = (out / f"{view}.md").read_text(encoding="utf-8")
        assert WORKBUDDY_CALIBER_LINE in md, view


def test_workbuddy_caliber_line_and_readme_share_the_same_wording() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for phrase in (
        "usage-log.json",
        "recentDates",
        "使用天数",
        "按使用天数计",
        "view_count",
        "patch_count",
        "last_used_at",
        "lastUsedDate",
        "orphan_ledger_entry",
    ):
        assert phrase in WORKBUDDY_CALIBER_LINE, phrase
        assert phrase in readme, phrase


def test_footer_is_conditional_for_a_workbuddy_root_without_records(
    hermes_root, tmp_path
) -> None:
    """A WorkBuddy root that exists but contributes nothing still counts as
    'in the run' (RunResult.sources criterion)."""
    empty_wb = tmp_path / "wb-empty"
    (empty_wb / "skills").mkdir(parents=True)
    out = tmp_path / "out"
    assert (
        main(
            [
                "inventory",
                "--hermes-root", str(hermes_root),
                "--workbuddy-root", str(empty_wb),
                "--out", str(out),
                "--format", "json",
            ]
        )
        == 0
    )
    doc = json.loads((out / "inventory.json").read_text(encoding="utf-8"))
    assert doc["footer"][-1] == WORKBUDDY_CALIBER_LINE


# ----------------------------------------------------------------- S4-1 -------
def _ledger_root(tmp_path: Path) -> Path:
    root = tmp_path / "wb"
    _write_skill(root / "skills" / "S1", "S1")
    _write_skill(root / "skills" / "S2", "S2")
    (root / "usage-log.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skills": {
                    "S1": {"type": "skill", "recentDates": ["2025-04-02"],
                           "lastUsedDate": "2025-04-02"},
                    # non-skill entry sharing nothing with the tree:
                    "S2-MCP": {"type": "mcp", "recentDates": ["2025-04-03"],
                               "lastUsedDate": "2025-04-03"},
                    # orphan key (no such skill directory):
                    "GHOST": {"type": "skill", "recentDates": ["2025-04-04"],
                              "lastUsedDate": "2025-04-04"},
                },
            }
        ),
        encoding="utf-8",
    )
    return root


def test_provenance_shares_usage_filtering(tmp_path) -> None:
    reporter = NullReporter()
    adapter = WorkBuddyAdapter(reporter)
    root = _ledger_root(tmp_path)

    usage = adapter.usage(root)
    provenance = adapter.provenance(root)

    assert set(usage) == {"S1"}
    assert set(provenance) == {"S1"}
    # No evidence may exist for a key that has no usage record.
    assert set(provenance) <= set(usage)
    assert provenance["S1"][0].kind == "usage_log"
    assert provenance["S1"][0].observed_at == "2025-04-02"
    # orphan warned exactly once, and never in provenance
    orphans = [w for w in reporter.warnings if "orphan_ledger_entry" in w]
    assert len(orphans) == 1 and "GHOST" in orphans[0]


def test_orphan_warning_emitted_once_regardless_of_call_order(tmp_path) -> None:
    root = _ledger_root(tmp_path)
    for first in ("provenance", "usage"):
        reporter = NullReporter()
        adapter = WorkBuddyAdapter(reporter)
        # provenance first, then usage (and the reverse) -> one warning only
        if first == "provenance":
            adapter.provenance(root)
            adapter.usage(root)
        else:
            adapter.usage(root)
            adapter.provenance(root)
        orphans = [w for w in reporter.warnings if "orphan_ledger_entry" in w]
        assert len(orphans) == 1, (first, reporter.warnings)


def test_cli_evidence_and_usage_never_contradict(tmp_path) -> None:
    root = _ledger_root(tmp_path)
    out = tmp_path / "out"
    assert (
        main(["inventory", "--workbuddy-root", str(root), "--out", str(out),
              "--format", "json"])
        == 0
    )
    records = json.loads((out / "records.json").read_text(encoding="utf-8"))
    for record in records["records"]:
        has_evidence = any(
            ev["kind"] == "usage_log" for ev in record["provenance"]
        )
        assert has_evidence == (record["usage"]["evidence_source"] == "usage_log")


# ----------------------------------------------------------------- S4-2 -------
def test_path_is_archived_matches_whole_segments_only() -> None:
    assert path_is_archived(".archive/old") is True
    assert path_is_archived("nested/.archive/old") is True
    assert path_is_archived(".archived-2024/deep") is True
    assert path_is_archived("nested/.archived") is True
    # substrings inside otherwise normal names must NOT count
    assert path_is_archived("plain.archive-helper") is False
    assert path_is_archived(".archive-helper") is False
    assert path_is_archived("archive/helper") is False
    assert path_is_archived("x.archived") is False


def test_scan_skills_presence_uses_segment_matching(tmp_path) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir / "normal", "normal")
    _write_skill(skills_dir / "plain.archive-helper", "plain-helper")
    _write_skill(skills_dir / ".archive" / "old", "old")
    _write_skill(skills_dir / ".archived-2024" / "deeper", "deeper")

    scanned = {item.rel_dir: item.presence for item in scan_skills(skills_dir)}
    assert scanned["normal"] == "active"
    assert scanned["plain.archive-helper"] == "active"
    assert scanned[".archive/old"] == "archived"
    assert scanned[".archived-2024/deeper"] == "archived"


def test_all_three_adapters_share_the_archive_segment_rules(tmp_path) -> None:
    """Unified caliber: hermes, openclaw and workbuddy all treat
    ``plain.archive-helper`` as active and ``.archive/x`` as archived."""
    hermes_root = tmp_path / "hermes"
    _write_skill(hermes_root / "skills" / "plain.archive-helper", "plain-helper")
    _write_skill(hermes_root / "skills" / ".archive" / "h-old", "old")

    openclaw_root = tmp_path / "openclaw"
    _write_skill(
        openclaw_root / "workspace" / "skills" / "plain.archive-helper", "plain-helper"
    )
    _write_skill(openclaw_root / "workspace" / "skills" / ".archive" / "o-old", "old")

    wb_root = tmp_path / "wb"
    _write_skill(wb_root / "skills" / "plain.archive-helper", "plain-helper")
    _write_skill(wb_root / "skills" / ".archive" / "w-old", "old")

    hermes = {r.name: r.presence for r in HermesAdapter(NullReporter()).discover(hermes_root)}
    openclaw = {
        r.name: r.presence for r in OpenClawAdapter(NullReporter()).discover(openclaw_root)
    }
    workbuddy = {
        r.name: r.presence for r in WorkBuddyAdapter(NullReporter()).discover(wb_root)
    }

    for table in (hermes, openclaw, workbuddy):
        assert table["plain-helper"] == "active"
        assert table["old"] == "archived"
    assert ARCHIVE_MARKERS == (".archive", ".archived*")


def test_workbuddy_skip_segments_are_anchored() -> None:
    is_skipped = WorkBuddyAdapter._is_skipped_segment
    assert is_skipped("wb-demo.bak-20250401") is True
    assert is_skipped("_hidden") is True
    assert is_skipped("_bm_skillid_migration.json") is True
    # no over-matching: the ``.bak-`` token must be a whole ``*.bak-*`` match
    assert is_skipped("sbak-1") is False
    assert is_skipped("x_bak-y") is False
    assert is_skipped("bak-2025") is False
    assert is_skipped("wb-demo") is False


# ----------------------------------------------------------------- S4-3 -------
def _strip_volatile(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("generated_at", None)
    doc.pop("footer", None)
    for section in doc.get("sections", []):
        for row in section.get("rows", []):
            if len(row) >= 7:
                row[6] = "<CTIME>"
    return doc


def test_examples_out_is_regenerated_and_consistent(
    hermes_root, openclaw_root, tmp_path
) -> None:
    examples = REPO_ROOT / "examples" / "out"
    assert (examples / "records.json").is_file(), "examples/out must ship records.json"

    fresh = tmp_path / "out"
    assert (
        main(
            [
                "report",
                "--hermes-root", str(hermes_root),
                "--openclaw-root", str(openclaw_root),
                "--since", "2025-01-01",
                "--out", str(fresh),
                "--format", "md,json",
            ]
        )
        == 0
    )

    # records.json is timestamp-free -> must be byte identical
    assert (examples / "records.json").read_text(encoding="utf-8") == (
        fresh / "records.json"
    ).read_text(encoding="utf-8")

    for view in ("inventory", "mirror", "report"):
        got = _strip_volatile(json.loads((fresh / f"{view}.json").read_text(encoding="utf-8")))
        base = _strip_volatile(json.loads((examples / f"{view}.json").read_text(encoding="utf-8")))
        assert got == base, f"examples/out/{view}.json is stale"

    # the committed artifacts carry the v0.1 (five-line) footer
    inventory = json.loads((examples / "inventory.json").read_text(encoding="utf-8"))
    assert tuple(inventory["footer"]) == CALIBER_FOOTER

    # examples/out/usage.json is the all-time window (separate usage run)
    usage = json.loads((examples / "usage.json").read_text(encoding="utf-8"))
    assert usage["summary"]["window"] == "all-time"


def test_examples_out_reports_have_five_line_footers() -> None:
    examples = REPO_ROOT / "examples" / "out"
    for name in ("inventory", "usage", "mirror", "report"):
        doc = json.loads((examples / f"{name}.json").read_text(encoding="utf-8"))
        assert tuple(doc["footer"]) == CALIBER_FOOTER, name
