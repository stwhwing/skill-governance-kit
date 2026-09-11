"""QA-independent *regression net* (Edward).

These probes documented known defects (see the QA report, round 1: 2x S2,
5x S3, 2x S4). The engineer fixed them at the root; the ``xfail`` markers have
been removed so this file now asserts the CORRECT behaviour permanently.

Findings covered:
  S2  skill_id / card-filename redaction bypass for sensitive directory names
  S2  trajectory over-count: any `path` key outside a tool call is counted
  S3  sanitize_obj does not sanitize dict *keys*
  S3  trajectory ignores nested skills/<cat>/<name>/SKILL.md
  S3  mirror_of pairs an active skill with an *archived* same-name counterpart
  S3  over-redaction: long uppercase / hex / base64-ish content -> <CHANNEL_ID>
  S3  bare channel prefixes (wr-K / o9-cq) left in cleartext in source
  S3  [project.urls] Homepage still a placeholder domain (example.invalid)
  S4  --out pointing at a file surfaces as exit 1 instead of a clean exit 2
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from skillgov.cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
from qa_data import CHAN, IPV4, MARK_A, SECRET  # noqa: E402


# S2 ---------------------------------------------------------------- S2 ------
def test_sensitive_directory_name_does_not_leak_via_skill_id(tmp_path):
    root = tmp_path / "h"
    d = root / "skills" / IPV4
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: dir-as-ip\n---\n\nb\n", encoding="utf-8")
    out = tmp_path / "out"
    assert main(["inventory", "--hermes-root", str(root), "--out", str(out),
                 "--format", "json"]) == 0
    blob = (out / "inventory.json").read_text(encoding="utf-8")
    dash_ip = IPV4.replace(".", "-")
    assert dash_ip not in blob, "IPv4 leaked in dash-slug form inside skill_id"
    assert IPV4 not in blob, "IPv4 leaked verbatim inside inventory"


def test_card_filename_is_not_a_redaction_bypass(tmp_path):
    root = tmp_path / "h"
    d = root / "skills" / IPV4
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: dir-as-ip\n---\n\nb\n", encoding="utf-8")
    out = tmp_path / "out"
    # The inventory carries the *sanitized* id; the raw dotted form must resolve
    # to the same record through the redaction gate (lookup is normalized).
    assert main(["inventory", "--hermes-root", str(root), "--out", str(out),
                 "--format", "json"]) == 0
    assert main(["card", "hermes:" + IPV4, "--hermes-root", str(root),
                 "--out", str(out)]) == 0
    dash_ip = IPV4.replace(".", "-")
    for produced in out.iterdir():
        assert IPV4 not in produced.name, f"IPv4 leaked in filename: {produced.name}"
        assert dash_ip not in produced.name, f"dash-form leaked: {produced.name}"


def test_trajectory_path_key_outside_toolcall_is_not_counted(tmp_path):
    from skillgov.adapters.trajectory import iter_trajectory_files, parse_trajectory_files
    d = tmp_path / "agents" / "a"
    d.mkdir(parents=True)
    line = json.dumps({"type": "config", "data": {"note": {
        "path": "workspace/skills/ghost-x/SKILL.md"}}})
    (d / "t.jsonl").write_text(line + "\n", encoding="utf-8")
    res = parse_trajectory_files(iter_trajectory_files(tmp_path / "agents"))
    assert res.strict_use == {}, "non-tool-call path inflated use_count"


# S3 ----------------------------------------------------------------- S3 -----
def test_sanitize_obj_redacts_sensitive_keys():
    from skillgov.sanitize import sanitize_obj
    res = sanitize_obj({IPV4: "v", CHAN: "v", MARK_A: "v"})
    joined = " ".join(res.keys())
    assert IPV4 not in joined and CHAN not in joined and MARK_A not in joined


def test_trajectory_nested_skill_path_is_counted(tmp_path):
    from skillgov.adapters.trajectory import iter_trajectory_files, parse_trajectory_files
    d = tmp_path / "agents" / "a"
    d.mkdir(parents=True)
    line = json.dumps({"type": "message", "data": {"messages": [{"role": "assistant",
        "content": [{"type": "toolCall", "toolName": "skill_view",
                     "arguments": {"path": "workspace/skills/team/demo-nested/SKILL.md"}}]}]}})
    (d / "t.jsonl").write_text(line + "\n", encoding="utf-8")
    res = parse_trajectory_files(iter_trajectory_files(tmp_path / "agents"))
    assert res.strict_use.get("demo-nested") == 1


def test_mirror_of_prefers_active_counterpart(tmp_path):
    hroot = tmp_path / "h"
    oroot = tmp_path / "o"
    for rel in ("skills/demo-alpha", "skills/.archive/demo-alpha"):
        d = hroot / rel
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: demo-alpha\ndescription: s\n---\n\nb\n",
                                    encoding="utf-8")
    d = oroot / "workspace" / "skills" / "demo-alpha"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: demo-alpha\ndescription: s\n---\n\nb\n", encoding="utf-8")
    from skillgov.cli.main import collect
    from skillgov.config import Config
    from skillgov.logging_setup import NullReporter
    result = collect(Config(hermes_root=hroot, openclaw_root=oroot), NullReporter())
    by_id = {r.skill_id: r for r in result.records}
    assert by_id["openclaw:demo-alpha"].mirror_of == "hermes:demo-alpha"


def test_long_uppercase_content_is_not_destroyed():
    from skillgov.sanitize import sanitize
    text = "OPENSOURCEALTERNATIVES"  # 23 uppercase letters, legitimate words
    assert sanitize(text) == text


def test_repo_has_no_bare_channel_prefix():
    for rel in ("src/skillgov/sanitize.py", "tests/test_sanitize.py",
                "tests/qa_independent/qa_data.py"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "wr" + "K" not in text, f"bare prefix in {rel}"
        assert "o9" + "cq" not in text, f"bare prefix in {rel}"


def test_no_placeholder_project_url():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert ".invalid" not in pyproject


# S4 ----------------------------------------------------------------- S4 -----
def test_out_pointing_at_file_is_cli_error(basic_roots, tmp_path):
    hroot, _ = basic_roots
    afile = tmp_path / "afile"
    afile.write_text("x", encoding="utf-8")
    assert main(["inventory", "--hermes-root", str(hroot), "--out", str(afile)]) == 2


def test_no_secret_literal_in_own_probe_files():
    """Guard: the QA probe files themselves must not contain a red-line literal."""
    for p in Path(__file__).parent.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert IPV4 not in text and SECRET not in text
