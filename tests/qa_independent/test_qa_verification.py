"""QA-independent *verification* tests (Edward).

These assert behaviour that survived my adversarial probes: they are expected to
PASS on the current code and serve as an independent regression net.

They deliberately use my own fixtures and my own measurement methods (raw
byte/digest comparison, subprocess CLIs) rather than the engineer's helpers.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from skillgov.cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
from qa_data import ALL_SENSITIVE, IPV4  # noqa: E402  (same-dir helper module)


# ---------------------------------------------------------------- helpers ----
def _manifest(root: Path) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            try:
                st = p.stat()
                out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns,
                                                 hashlib.sha256(p.read_bytes()).hexdigest())
            except OSError:
                pass
    return out


def _run_cli(args, cwd):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run([sys.executable, "-m", "skillgov", *args],
                          cwd=str(cwd), env=env, capture_output=True, text=True)


def _strip_generated(text: str) -> str:
    doc = json.loads(text)
    doc.pop("generated_at", None)
    return json.dumps(doc, sort_keys=True, ensure_ascii=False)


# ------------------------------------------------------- redaction (values) --
def test_sensitive_values_are_redacted_in_md_and_json(sensitive_hermes_root, tmp_path):
    out = tmp_path / "out"
    code = main(["report", "--hermes-root", str(sensitive_hermes_root),
                 "--out", str(out), "--format", "md,json"])
    assert code == 0
    for path in out.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for label, token in ALL_SENSITIVE.items():
            assert token not in text, f"{label} leaked in {path.name}"
    for path in out.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for label, token in ALL_SENSITIVE.items():
            assert token not in text, f"{label} leaked in {path.name}"
    # sanity: the placeholders actually appear (we are not asserting on empty output)
    assert "<SERVER>" in (out / "inventory.md").read_text(encoding="utf-8")


def test_no_absolute_machine_path_in_report(sensitive_hermes_root, tmp_path):
    out = tmp_path / "out"
    assert main(["inventory", "--hermes-root", str(sensitive_hermes_root),
                 "--out", str(out), "--format", "json"]) == 0
    doc = json.loads((out / "inventory.json").read_text(encoding="utf-8"))
    blob = json.dumps(doc)
    assert str(tmp_path) not in blob
    assert "/root/" not in blob and "C:\\" not in blob


# ----------------------------------------------------------- read-only -------
def test_all_readonly_subcommands_write_nothing_to_the_roots(basic_roots, tmp_path):
    hroot, oroot = basic_roots
    common = ["--hermes-root", str(hroot), "--openclaw-root", str(oroot)]
    commands = [
        ["inventory", *common],
        ["usage", *common],
        ["card", "hermes:demo-alpha", *common],
        ["mirror", *common],
        ["report", *common],
    ]
    before_h, before_o = _manifest(hroot), _manifest(oroot)
    for cmd in commands:
        _run_cli([*cmd, "--out", str(tmp_path / "out")], tmp_path)
    assert _manifest(hroot) == before_h
    assert _manifest(oroot) == before_o


def test_readonly_usage_file_still_succeeds(basic_roots, tmp_path):
    hroot, oroot = basic_roots
    usage = hroot / "skills" / ".usage.json"
    os.chmod(usage, stat.S_IREAD)
    code = main(["report", "--hermes-root", str(hroot), "--openclaw-root", str(oroot),
                 "--out", str(tmp_path / "out"), "--format", "json"])
    assert code == 0
    assert not (usage.stat().st_mode & stat.S_IWRITE)


# --------------------------------------------------------- idempotency -------
def test_three_runs_are_byte_identical_except_generated_at(basic_roots, tmp_path):
    hroot, oroot = basic_roots
    blobs, raws = [], []
    for i in range(3):
        out = tmp_path / f"out{i}"
        assert main(["report", "--hermes-root", str(hroot), "--openclaw-root", str(oroot),
                     "--out", str(out), "--format", "json"]) == 0
        blobs.append({n: _strip_generated((out / f"{n}.json").read_text())
                      for n in ("inventory", "usage", "mirror", "report")})
        raws.append(out)
    assert blobs[0] == blobs[1] == blobs[2]
    # the ONLY differing raw line is generated_at
    a = (raws[0] / "report.json").read_text().splitlines()
    b = (raws[1] / "report.json").read_text().splitlines()
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    assert all("generated_at" in a[i] for i in diff)


def test_order_is_stable_under_directory_name_shuffle(basic_roots, tmp_path):
    hroot, oroot = basic_roots
    for nm in ("zzz-skill", "aaa-skill"):
        d = hroot / "skills" / nm
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {nm}\ndescription: order\n---\n\nb\n", encoding="utf-8")
    ids = []
    for i in range(2):
        out = tmp_path / f"s{i}"
        assert main(["inventory", "--hermes-root", str(hroot), "--out", str(out),
                     "--format", "json"]) == 0
        doc = json.loads((out / "inventory.json").read_text())
        ids.append([row[0] for row in doc["sections"][0]["rows"]])
    assert ids[0] == ids[1] == sorted(ids[0])


# -------------------------------------------------------------- exit codes ---
def test_exit_codes_zero_two_three(basic_roots, tmp_path):
    hroot, oroot = basic_roots
    assert main(["inventory", "--hermes-root", str(hroot), "--out", str(tmp_path / "o")]) == 0
    assert main(["inventory", "--hermes-root", str(hroot), "--format", "xml",
                 "--out", str(tmp_path / "o")]) == 2
    assert main(["usage", "--hermes-root", str(hroot), "--since", "nope",
                 "--out", str(tmp_path / "o")]) == 2
    assert main(["card", "hermes:missing", "--hermes-root", str(hroot),
                 "--out", str(tmp_path / "o")]) == 2
    assert main(["inventory", "--out", str(tmp_path / "o")]) == 3


# --------------------------------------------------- trajectory dispatch -----
def _parse(lines, tmp, max_bytes=None):
    from skillgov.adapters.trajectory import iter_trajectory_files, parse_trajectory_files
    from skillgov.logging_setup import NullReporter
    d = Path(tmp) / "agents" / "main" / "agent"
    d.mkdir(parents=True, exist_ok=True)
    (d / "t.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rep = NullReporter()
    return parse_trajectory_files(iter_trajectory_files(Path(tmp) / "agents"),
                                  max_bytes=max_bytes, reporter=rep), rep


SNAP = json.dumps({"type": "session_snapshot", "data": {"skills": {"entries": {
    "demo-alpha": {"name": "demo-alpha"}, "ghost": {"name": "ghost"}}}, "messages": []}})
TOOL = json.dumps({"type": "message", "data": {"messages": [{"role": "assistant", "content": [
    {"type": "toolCall", "toolName": "skill_view",
     "arguments": {"path": "workspace/skills/demo-alpha/SKILL.md"}}]}]}})
BODY = json.dumps({"type": "message", "data": {"messages": [{"role": "user", "content": [
    {"type": "text", "text": "read skills/demo-gamma/SKILL.md"}]}]}})


def test_trajectory_snapshot_entries_never_counted(tmp_path):
    res, _ = _parse([SNAP], tmp_path)
    assert res.strict_use == {}
    assert "ghost" in res.snapshot_names


def test_trajectory_arguments_path_counted(tmp_path):
    res, _ = _parse([TOOL], tmp_path)
    assert res.strict_use == {"demo-alpha": 1}


def test_trajectory_mixed_prefers_arguments(tmp_path):
    res, _ = _parse([SNAP, TOOL, BODY], tmp_path)
    assert res.strict_use == {"demo-alpha": 1}
    assert res.mentions.get("demo-gamma") == 1


def test_trajectory_bad_line_degrades_not_crashes(tmp_path):
    res, rep = _parse([TOOL, "{ broken", TOOL], tmp_path)
    assert res.strict_use == {"demo-alpha": 2}
    assert res.bad_lines == 1
    assert any("bad_jsonl" in w for w in rep.warnings)


def test_trajectory_max_bytes_warns_and_degrades(tmp_path):
    res, rep = _parse([TOOL] * 500, tmp_path, max_bytes=64)
    assert res.files_truncated == ["t.jsonl"]
    assert any("truncated_input" in w for w in rep.warnings)


# ------------------------------------------------- cross-ecosystem usage -----
def test_same_name_usage_is_not_cross_contaminated(basic_roots):
    hroot, oroot = basic_roots
    from skillgov.adapters.hermes import HermesAdapter
    from skillgov.adapters.openclaw import OpenClawAdapter
    from skillgov.logging_setup import NullReporter
    hu = HermesAdapter(NullReporter()).usage(hroot)
    ou = OpenClawAdapter(NullReporter()).usage(oroot)
    assert hu["demo-alpha"].use_count == 7
    assert ou["demo-alpha"].use_count == 1


# -------------------------------------------------- static hygiene -----------
def test_source_compiles_and_imports_cleanly():
    mods = []
    for p in sorted(SRC_DIR.rglob("*.py")):
        rel = p.relative_to(SRC_DIR).with_suffix("")
        name = ".".join(rel.parts)
        if not name.endswith("__main__"):
            mods.append(name)
    for name in mods:
        importlib.import_module(name)


def test_engineer_redline_token_set_is_absent_from_repo():
    """Reproduce the engineer's own scan contract (their exact token set)."""
    eng_tokens = [
        "111." + "229." + "70." + "191",
        "light" + "make.site",
        "api." + "skill" + "hub.cn",
        "wr" + "K" + "AQISgAA",
        "\u541e\u5c0f\u54e5",
        "\u541e\u5c0f\u59b9",
        "/root" + "/.hermes",
        "/root" + "/.openclaw",
        "open" + "claw.json",
        "config" + ".yaml",
    ]
    hits = []
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file() or any(x in {".git", "__pycache__", ".pytest_cache"} for x in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for t in eng_tokens:
            if t in text:
                hits.append(str(p.relative_to(REPO_ROOT)))
    assert hits == []
