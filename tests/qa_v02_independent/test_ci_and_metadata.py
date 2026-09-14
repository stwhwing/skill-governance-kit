"""v0.2 spec B/D + metadata verification (Edward / QA).

NOTE: PyYAML is intentionally NOT installed (the project forbids third-party
runtime deps and QA may not add any), so the CI file is validated structurally
via regex over the indentation-preserving text, covering exactly the required
checks: trigger, matrix (os x python), runner, commands and the "no third-party
action" rule.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from conftest import REPO_ROOT, run_cli

CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"


# ---------------------------------------------------------------- CI (spec B) --
def _ci_text() -> str:
    return CI.read_text(encoding="utf-8")


def test_ci_triggers_on_push_and_pull_request():
    text = _ci_text()
    assert re.search(r"^on:\s*\[.*push.*\].*$", text, re.M) or (
        re.search(r"^on:\s*$", text, re.M) and "push:" in text and "pull_request:" in text
    ), "CI must trigger on push and pull_request"


def test_ci_matrix_os_and_python():
    text = _ci_text()
    os_line = re.search(r"os:\s*\[(.*?)\]", text)
    py_line = re.search(r"python:\s*\[(.*?)\]", text)
    assert os_line and py_line, "matrix must define os and python"
    oses = [x.strip().strip('"') for x in os_line.group(1).split(",")]
    pys = [x.strip().strip('"') for x in py_line.group(1).split(",")]
    assert set(oses) == {"ubuntu-latest", "windows-latest"}, oses
    assert set(pys) == {"3.11", "3.13"}, pys


def test_ci_runner_uses_matrix():
    assert "runs-on: ${{ matrix.os }}" in _ci_text()


def test_ci_runs_pytest():
    assert re.search(r"run:\s*python -m pytest", _ci_text()), "CI must run pytest"


def test_ci_has_no_third_party_action():
    uses = re.findall(r"uses:\s*(\S+)", _ci_text())
    assert uses, "expected at least one action"
    for action in uses:
        assert action.startswith("actions/"), f"third-party action not allowed: {action}"


def test_ci_yaml_is_structurally_sane():
    text = _ci_text()
    assert "\t" not in text, "YAML must not contain tabs"
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        assert indent % 2 == 0, f"odd indentation: {raw!r}"


# ------------------------------------------------------------ metadata (D) -----
def test_version_is_0_2_0_everywhere():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == "0.2.0"
    import skillgov
    assert skillgov.__version__ == "0.2.0"


def test_dependencies_are_empty():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == []


def test_version_cli_reports_0_2_0(tmp_path):
    proc = run_cli(["--version"], tmp_path)
    assert "0.2.0" in (proc.stdout + proc.stderr), proc.stdout + proc.stderr


def test_help_exposes_new_flags(tmp_path):
    proc = run_cli(["inventory", "--help"], tmp_path)
    out = proc.stdout + proc.stderr
    assert "--workbuddy-root" in out
    assert "--assert-readonly" in out
