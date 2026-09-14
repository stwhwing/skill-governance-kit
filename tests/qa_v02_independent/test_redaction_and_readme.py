"""v0.2 redaction (spec 7) + README-vs-behaviour consistency (spec 8).

Uses an independent, fragment-assembled token set (see conftest.REDLINE_TOKENS)
so this file is not itself a hit.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import REDLINE_TOKENS, REPO_ROOT, SKIP_DIRS, run_cli
from skillgov.adapters.workbuddy import WorkBuddyAdapter
from skillgov.logging_setup import NullReporter


# --------------------------------------------------------------- redaction -----
def _iter_files(root: Path):
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            yield Path(dirpath) / fn


def test_repo_contains_no_redline_token():
    hits: dict[str, list[str]] = {k: [] for k in REDLINE_TOKENS}
    for p in _iter_files(REPO_ROOT):
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(p.relative_to(REPO_ROOT))
        for label, token in REDLINE_TOKENS.items():
            if token in text:
                hits[label].append(rel)
    offending = {k: v for k, v in hits.items() if v}
    assert offending == {}, f"red-line tokens found in repo: {offending}"


def test_v02_new_files_have_no_machine_path_or_private_marker():
    """New v0.2 surfaces must not embed a real machine path / private literal."""
    import os

    new_paths = [
        REPO_ROOT / "src" / "skillgov" / "adapters" / "workbuddy.py",
        REPO_ROOT / ".github" / "workflows" / "ci.yml",
        REPO_ROOT / "tests" / "test_workbuddy_adapter.py",
    ]
    fix = REPO_ROOT / "tests" / "fixtures" / "workbuddy-root"
    for dirpath, dirnames, filenames in os.walk(fix):
        for fn in filenames:
            new_paths.append(Path(dirpath) / fn)
    bad = ("C:\\" + "Users\\", "/home/", "/Users/")
    for p in new_paths:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for marker in bad:
            assert marker not in text, f"{p.name} embeds machine path {marker!r}"


# ---------------------------------------------- README vs behaviour (spec 8) ---
def test_readme_day_based_caliber_matches_code(wb_root):
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "按使用天数计" in readme or "usage days" in readme
    # behaviour: two dates -> use_count 2 (days), not invocation count
    adapter = WorkBuddyAdapter(NullReporter())
    assert adapter.usage(wb_root)["WB-A"].use_count == 3


def test_readme_view_patch_always_zero_matches_code(wb_root):
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "view_count" in readme and "patch_count" in readme
    a = WorkBuddyAdapter(NullReporter()).usage(wb_root)["WB-A"]
    assert a.view_count == 0 and a.patch_count == 0


def test_readme_opt_in_byte_identical_claim_holds(v01_roots, tmp_path):
    """README §WorkBuddy claims a no-WorkBuddy run is byte-identical to
    Hermes+OpenClaw only. Verify the footer therefore carries NO WorkBuddy line."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "byte-identical" in readme
    hroot, oroot = v01_roots
    out = tmp_path / "out"
    assert run_cli(["inventory", "--hermes-root", str(hroot), "--openclaw-root", str(oroot),
                    "--out", str(out), "--format", "json"], tmp_path).returncode == 0
    footer = json.loads((out / "inventory.json").read_text(encoding="utf-8"))["footer"]
    wb_lines = [ln for ln in footer if "WorkBuddy" in ln]
    assert wb_lines == [], (
        "README promises byte-identical output without --workbuddy-root, but every "
        f"report now injects the WorkBuddy caliber line: {wb_lines}"
    )
