"""QA-independent fixture builders (Edward). No dependency on the engineer's conftest.

Everything here is synthetic and hermetic: fixtures are built under pytest's
``tmp_path`` so the repository's own fixtures and source tree are never touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qa_data import (  # noqa: E402
    CHAN,
    CONFIGFILE,
    IPV4,
    MARK_A,
    MARK_B,
    NICK_HM,
    NICK_OC,
    ROOT_HM,
    SECRET,
)


def _write_skill(dir_path: Path, *, name: str, description: str, version: str = "1.0.0") -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\nversion: {version}\n---\n\n# body\n",
        encoding="utf-8",
    )


@pytest.fixture
def sensitive_hermes_root(tmp_path: Path) -> Path:
    """A Hermes root whose *values* embed every red-line shape."""
    root = tmp_path / "hermes-root"
    skills = root / "skills"
    desc = (
        f"endpoint {IPV4} market {MARK_A} {MARK_B} channel {CHAN} "
        f"n {NICK_OC} {NICK_HM} root {ROOT_HM} key {SECRET} file {CONFIGFILE} "
        "demo-alpha 2025-01-01T00:00:00Z https://example.com/path"
    )
    _write_skill(skills / "demo-alpha", name="demo-alpha", description=desc)
    (skills / ".usage.json").write_text(
        json.dumps({"demo-alpha": {"use_count": 5, "state": "active"}}), encoding="utf-8"
    )
    return root


@pytest.fixture
def basic_roots(tmp_path: Path) -> tuple[Path, Path]:
    """A minimal, noise-free Hermes + OpenClaw pair (one mirrored skill)."""
    hroot = tmp_path / "hermes-root"
    oroot = tmp_path / "openclaw-root"
    _write_skill(hroot / "skills" / "demo-alpha", name="demo-alpha", description="same")
    _write_skill(hroot / "skills" / "demo-beta", name="demo-beta", description="beta")
    _write_skill(oroot / "workspace" / "skills" / "demo-alpha", name="demo-alpha", description="same")
    (hroot / "skills" / ".usage.json").write_text(
        json.dumps({"demo-alpha": {"use_count": 7, "last_used_at": "2025-02-01T00:00:00Z"}}),
        encoding="utf-8",
    )
    agents = oroot / "agents" / "main" / "agent"
    agents.mkdir(parents=True)
    line = json.dumps({"type": "message", "data": {"messages": [
        {"role": "assistant", "content": [
            {"type": "toolCall", "toolName": "skill_view",
             "arguments": {"path": "workspace/skills/demo-alpha/SKILL.md"}}]}]}})
    (agents / "trajectory.jsonl").write_text(line + "\n", encoding="utf-8")
    return hroot, oroot
