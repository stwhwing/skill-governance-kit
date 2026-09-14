"""v0.2 spec E — backward-compatibility verification (Edward / QA).

Contract under test (spec E / README §WorkBuddy / code comment in
``report/inventory.py``): *when ``--workbuddy-root`` is NOT supplied, the output
must be byte-identical to v0.1 except for ``generated_at``.*

Baseline: GitHub ``main`` == v0.1.0 (``src/skillgov/report/render.py``) and the
committed ``examples/out/*`` artifacts.  v0.1's ``CALIBER_FOOTER`` has exactly
five lines and none mention WorkBuddy.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import REPO_ROOT, V01_FOOTER, run_cli

VIEWS = ("inventory", "usage", "mirror", "report")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v01_baseline_footer_is_five_lines_without_workbuddy():
    """Sanity: the committed v0.1 baseline really has a 5-line footer."""
    doc = _read_json(REPO_ROOT / "examples" / "out" / "inventory.json")
    assert tuple(doc["footer"]) == V01_FOOTER
    assert not any("WorkBuddy" in line for line in doc["footer"])


def test_no_workbuddy_run_footer_matches_v01_baseline(v01_roots, tmp_path):
    """E / S1: footer must stay identical when WorkBuddy is not part of the run."""
    hroot, oroot = v01_roots
    out = tmp_path / "out"
    proc = run_cli(["report", "--hermes-root", str(hroot),
                    "--openclaw-root", str(oroot), "--since", "2025-01-01",
                    "--out", str(out), "--format", "json"], tmp_path)
    assert proc.returncode == 0, proc.stderr
    for view in VIEWS:
        doc = _read_json(out / f"{view}.json")
        extra = [ln for ln in doc["footer"] if ln not in V01_FOOTER]
        assert tuple(doc["footer"]) == V01_FOOTER, (
            f"{view}.json footer gained {len(doc['footer']) - len(V01_FOOTER)} "
            f"line(s) vs v0.1 -> NOT byte-identical. Extra={extra}"
        )


def test_no_workbuddy_run_matches_v01_baseline_except_footer(v01_roots, tmp_path):
    """Everything other than the footer is identical to the v0.1 baseline.

    This isolates the single regression: with the footer excluded, the payload
    (summary keys/values, sections, rows, warnings, title) is unchanged.

    Only ``inventory.json`` / ``report.json`` / ``mirror.json`` are compared:
    ``examples/out/usage.json`` was produced by a separate ``usage`` run without
    ``--since`` (window=all-time), so it is not comparable to a
    ``report --since 2025-01-01`` bundle.
    """
    hroot, oroot = v01_roots
    out = tmp_path / "out"
    proc = run_cli(["report", "--hermes-root", str(hroot),
                    "--openclaw-root", str(oroot), "--since", "2025-01-01",
                    "--out", str(out), "--format", "json"], tmp_path)
    assert proc.returncode == 0, proc.stderr
    for view in ("inventory", "mirror", "report"):
        got = _read_json(out / f"{view}.json")
        base = _read_json(REPO_ROOT / "examples" / "out" / f"{view}.json")
        for doc in (got, base):
            doc.pop("generated_at", None)
            doc.pop("footer", None)
        # created_at is a file ctime -> not reproducible across checkouts.
        for doc in (got, base):
            for sec in doc["sections"]:
                for row in sec.get("rows", []):
                    if len(row) >= 7:
                        row[6] = "<CTIME>"
        assert got == base, f"{view}.json payload differs from v0.1 baseline"


def test_opt_in_claim_is_workbuddy_line_only_difference(v01_roots, tmp_path):
    """Document the full delta of a no-WorkBuddy v0.2 run vs v0.1 exactly.

    Fails while the extra WorkBuddy footer line is unconditional; the assertion
    message enumerates the complete set of differing lines.
    """
    hroot, oroot = v01_roots
    out = tmp_path / "out"
    run_cli(["report", "--hermes-root", str(hroot), "--openclaw-root", str(oroot),
             "--out", str(out), "--format", "json"], tmp_path)
    got = _read_json(out / "inventory.json")
    assert len(got["footer"]) == len(V01_FOOTER), (
        f"delta = {len(got['footer']) - len(V01_FOOTER)} extra footer line(s): "
        f"{[ln for ln in got['footer'] if ln not in V01_FOOTER]}"
    )
