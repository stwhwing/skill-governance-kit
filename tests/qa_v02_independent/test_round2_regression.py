"""Round-2 independent regression net (Edward / QA).

Permanently captures the verification I ran for the S1 + S4-1/S4-2/S4-3 fix
round, independently of the engineer's ``tests/test_v02_fixes.py``:

* the conditional-footer **tri-state** boundary,
* provenance/usage key parity + single orphan warning + no card contradiction,
* segment-anchored archive/exclusion matching, and
* builder-level backward compatibility (v0.1-style call with no new kwarg).
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import REDLINE_TOKENS, REPO_ROOT, V01_FOOTER, run_cli, write_skill  # noqa: F401
from skillgov.adapters.fs_scan import ARCHIVE_MARKERS, path_is_archived
from skillgov.adapters.hermes import HermesAdapter
from skillgov.adapters.openclaw import OpenClawAdapter
from skillgov.adapters.workbuddy import WorkBuddyAdapter
from skillgov.cli.main import collect
from skillgov.config import Config
from skillgov.logging_setup import NullReporter
from skillgov.report.card import build_card
from skillgov.report.inventory import build_inventory
from skillgov.report.mirror import build_mirror
from skillgov.report.usage import build_usage

VIEWS = ("inventory", "usage", "mirror", "report")


def _footer_len(out: Path) -> int:
    return len(json.loads((out / "inventory.json").read_text(encoding="utf-8"))["footer"])


# ------------------------------------------------- S1 tri-state boundary -------
def test_footer_tristate_boundary(v01_roots, tmp_path):
    hroot, oroot = v01_roots

    # (i) workbuddy root WITH a usable skills dir -> 6 lines
    wb = tmp_path / "wb"
    write_skill(wb / "skills" / "S1", name="S1")
    (wb / "usage-log.json").write_text(json.dumps({"skills": {"S1": {"type": "skill"}}}),
                                       encoding="utf-8")
    o1 = tmp_path / "o1"
    assert run_cli(["inventory", "--workbuddy-root", str(wb), "--out", str(o1)], tmp_path).returncode == 0
    assert _footer_len(o1) == len(V01_FOOTER) + 1

    # (ii-a) workbuddy root but skills/ MISSING -> still 5 (ecosystem not counted)
    wb_missing = tmp_path / "wb_missing"
    wb_missing.mkdir()
    o2 = tmp_path / "o2"
    assert run_cli(["inventory", "--hermes-root", str(hroot), "--workbuddy-root",
                    str(wb_missing), "--out", str(o2)], tmp_path).returncode == 0
    assert _footer_len(o2) == len(V01_FOOTER)

    # (ii-b) workbuddy root with EMPTY skills dir -> 6 lines
    wb_empty = tmp_path / "wb_empty"
    (wb_empty / "skills").mkdir(parents=True)
    o3 = tmp_path / "o3"
    assert run_cli(["inventory", "--workbuddy-root", str(wb_empty), "--out", str(o3)],
                   tmp_path).returncode == 0
    assert _footer_len(o3) == len(V01_FOOTER) + 1

    # (iii) no workbuddy root -> 5 lines
    o4 = tmp_path / "o4"
    assert run_cli(["inventory", "--hermes-root", str(hroot), "--openclaw-root",
                    str(oroot), "--out", str(o4)], tmp_path).returncode == 0
    assert _footer_len(o4) == len(V01_FOOTER)


def test_no_workbuddy_run_never_mentions_workbuddy(v01_roots, tmp_path):
    hroot, oroot = v01_roots
    out = tmp_path / "out"
    assert run_cli(["report", "--hermes-root", str(hroot), "--openclaw-root", str(oroot),
                    "--since", "2025-01-01", "--out", str(out), "--format", "md,json"],
                   tmp_path).returncode == 0
    blob = "".join(p.read_text(encoding="utf-8") for p in out.iterdir())
    assert "workbuddy" not in blob.lower()


# ------------------------------------------------------------- S4-1 -----------
def test_provenance_and_usage_keys_are_equal(tmp_path):
    root = tmp_path / "wb"
    write_skill(root / "skills" / "WB-A", name="WB-A")
    write_skill(root / "skills" / "demo", name="demo")
    (root / "usage-log.json").write_text(json.dumps({"skills": {
        "WB-A": {"type": "skill", "recentDates": ["2025-04-01"], "lastUsedDate": "2025-04-01"},
        "demo": {"type": "mcp", "recentDates": ["2025-07-07"], "lastUsedDate": "2025-07-07"},
        "WB-ORPHAN": {"type": "skill", "recentDates": ["2025-01-02"], "lastUsedDate": "2025-01-02"},
    }}), encoding="utf-8")
    rep = NullReporter()
    ad = WorkBuddyAdapter(rep)
    usage = ad.usage(root)
    prov = ad.provenance(root)
    assert set(prov) == set(usage) == {"WB-A"}
    assert set(prov) <= set(usage)
    orphans = [w for w in rep.warnings if "orphan_ledger_entry" in w]
    assert len(orphans) == 1 and "WB-ORPHAN" in orphans[0]


def test_card_never_shows_usage_log_evidence_without_usage(tmp_path):
    root = tmp_path / "wb"
    write_skill(root / "skills" / "demo", name="demo")
    (root / "usage-log.json").write_text(json.dumps({"skills": {
        "demo": {"type": "mcp", "recentDates": ["2025-07-07"], "lastUsedDate": "2025-07-07"}}}),
        encoding="utf-8")
    out = tmp_path / "out"
    assert run_cli(["card", "workbuddy:demo", "--workbuddy-root", str(root),
                    "--out", str(out)], tmp_path).returncode == 0
    card = json.loads((out / "card-workbuddy-demo.json").read_text(encoding="utf-8"))
    usage_kv = dict(card["sections"][1]["items"])
    prov_rows = card["sections"][2]["rows"]
    assert usage_kv["evidence_source"] == "none"
    assert prov_rows == []


# ------------------------------------------------------------- S4-2 -----------
def test_archive_matching_is_segment_anchored():
    assert ARCHIVE_MARKERS == (".archive", ".archived*")
    for rel in (".archive/old", ".archived-2024/deep", "nested/.archived"):
        assert path_is_archived(rel) is True, rel
    for rel in ("x.archived", ".archive-helper", "plain.archive-helper"):
        assert path_is_archived(rel) is False, rel


def test_workbuddy_exclusion_is_anchored(tmp_path):
    root = tmp_path / "wb"
    for nm in ("keep-normal", "sbak-1", "x_bak-y", "bak-2025"):
        write_skill(root / "skills" / nm, name=nm)
    for nm in ("wb-demo.bak-20250401", "_hidden"):
        write_skill(root / "skills" / nm, name=nm)
    ids = {r.skill_id for r in WorkBuddyAdapter(NullReporter()).discover(root)}
    assert ids == {"workbuddy:keep-normal", "workbuddy:sbak-1",
                   "workbuddy:x_bak-y", "workbuddy:bak-2025"}


def test_hermes_and_openclaw_fixture_presence_unchanged(v01_roots):
    hroot, oroot = v01_roots
    hermes = {r.skill_id: r.presence for r in HermesAdapter(NullReporter()).discover(hroot)}
    openclaw = {r.skill_id: r.presence for r in OpenClawAdapter(NullReporter()).discover(oroot)}
    assert hermes == {"hermes:archive-demo-old": "archived",
                      "hermes:demo-alpha": "active",
                      "hermes:demo-beta": "active"}
    assert openclaw == {"openclaw:demo-alpha": "active", "openclaw:demo-gamma": "active"}


# ------------------------------------------- builder backward compatibility ----
def test_report_builders_default_to_v01_footer(v01_roots):
    hroot, oroot = v01_roots
    result = collect(Config(hermes_root=hroot, openclaw_root=oroot), NullReporter())
    # v0.1-style calls: no include_workbuddy_caliber kwarg at all.
    views = {
        "inventory": build_inventory(result.records, generated_at="X"),
        "usage": build_usage(result.records, generated_at="X"),
        "mirror": build_mirror(result.records, generated_at="X"),
        "card": build_card(result.records, "hermes:demo-alpha", generated_at="X"),
    }
    for name, view in views.items():
        assert tuple(view["footer"]) == V01_FOOTER, name
    assert len(build_inventory(result.records, generated_at="X",
                               include_workbuddy_caliber=True)["footer"]) == len(V01_FOOTER) + 1


# ------------------------------------------------------------- S4-3 -----------
def test_examples_out_ships_records_and_five_line_footers():
    ex = REPO_ROOT / "examples" / "out"
    assert (ex / "records.json").is_file()
    for name in VIEWS:
        doc = json.loads((ex / f"{name}.json").read_text(encoding="utf-8"))
        assert tuple(doc["footer"]) == V01_FOOTER, name
