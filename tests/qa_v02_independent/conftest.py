"""Independent v0.2 verification fixtures (Edward / QA).

Deliberately self-contained: this package does NOT reuse the engineer's
``tests/conftest.py`` fixtures or ``tests/qa_independent`` helpers. Everything
below builds its own synthetic trees under ``tmp_path`` so the repository's own
fixtures and source tree are never touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# --- red-line tokens, assembled from fragments (never raw in this file) -------
REDLINE_TOKENS = {
    "ipv4": "111." + "229." + "70." + "191",
    "market_a": "light" + "make.site",
    "market_b": "api." + "skill" + "hub.cn",
    "market_c": "skill" + "hub.cn",
    "market_d": "claw" + "hub.ai",
    "market_e": "claw" + "hub.cn",
    "chan_prefix1": "wr" + "K",
    "chan_prefix2": "o9" + "cq",
    "nick_oc": "\u541e\u5c0f\u54e5",
    "nick_hm": "\u541e\u5c0f\u59b9",
    "root_hermes": "/root" + "/.hermes",
    "root_openclaw": "/root" + "/.openclaw",
    "root_hermes_win": "\\root" + "\\.hermes",
    "root_openclaw_win": "\\root" + "\\.openclaw",
    "conf_openclaw": "open" + "claw.json",
    "conf_yaml": "config" + ".yaml",
    "conf_yml": "config" + ".yml",
    "win_home": "C:\\" + "Users\\",
}

# The documented v0.1 footer (5 lines, no WorkBuddy caliber line) — fetched from
# GitHub `main` (== v0.1.0) render.py and mirrored in examples/out/*.json.
V01_FOOTER = (
    "口径声明：Hermes 使用 = skill_view 标准加载（不含 read_file / terminal 直读）。",
    "口径声明：OpenClaw 使用 = 仅 trajectory 的 arguments.path 严口径计入 use_count；消息正文引用仅作旁证。",
    "口径声明：OpenClaw 会话快照内嵌技能目录（skills.entries）永不 计入使用。",
    "口径声明：全程只读采集；缺失数据源将降级并把原因记录到 warnings。",
    "口径声明：同输入重复运行，输出除 generated_at 外逐字节一致（幂等）。",
)

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


# ------------------------------------------------------------------ helpers ---
def run_cli(args, cwd) -> subprocess.CompletedProcess:
    """Run ``python -m skillgov <args>`` with ``src`` importable (subprocess)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run(
        [sys.executable, "-m", "skillgov", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


def write_skill(dir_path: Path, *, name: str, description: str = "demo",
                version: str = "1.0.0") -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\nversion: {version}\n---\n\n# body\n",
        encoding="utf-8",
    )


def manifest(root: Path) -> dict:
    """(relpath -> size, mtime_ns, sha256) for every file under *root*."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            try:
                st = p.stat()
                out[str(p.relative_to(root))] = (
                    st.st_size, st.st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()
                )
            except OSError:
                pass
    return out


def drop_keys(doc: dict, keys) -> dict:
    return {k: v for k, v in doc.items() if k not in keys}


# ------------------------------------------------------------------ fixtures --
@pytest.fixture
def v01_roots() -> tuple[Path, Path]:
    """The committed v0.1 fixtures (Hermes + OpenClaw only, no WorkBuddy)."""
    fix = REPO_ROOT / "tests" / "fixtures"
    return fix / "hermes-root", fix / "openclaw-root"


@pytest.fixture
def wb_root(tmp_path: Path) -> Path:
    """My own WorkBuddy tree covering every A-spec case."""
    root = tmp_path / "wb-root"
    write_skill(root / "skills" / "WB-A", name="WB-A")
    write_skill(root / "skills" / "WB-B", name="WB-B")
    write_skill(root / "skills" / "WB-C.bak-20250401", name="WB-C")  # excluded
    write_skill(root / "skills" / ".archive" / "WB-D", name="WB-D")  # archived
    write_skill(root / "skills" / "_hidden" / "WB-E", name="WB-E")   # excluded (_*)
    (root / "skills" / "_bm_skillid_migration.json").write_text("{}", encoding="utf-8")
    (root / "audit-log").mkdir(parents=True, exist_ok=True)
    (root / "audit-log" / "2025.jsonl").write_text(
        json.dumps({"skill": "WB-A", "event": "skill_view"}) + "\n", encoding="utf-8")
    write_skill(root / "plugins" / "cache" / "PC-SKILL", name="PC-SKILL")   # out of scope
    write_skill(root / "connectors" / "CONN-SKILL", name="CONN-SKILL")     # out of scope
    (root / "usage-log.json").write_text(json.dumps({
        "version": 1,
        "skills": {
            "WB-A": {"type": "skill", "firstSeenDate": "2025-04-01",
                     "recentDates": ["2025-04-03", "2025-04-04", "2025-04-05"],
                     "lastUsedDate": "2025-04-05"},
            "WB-B": {"type": "skill", "firstSeenDate": "2025-04-01",
                     "recentDates": [], "lastUsedDate": None},
            "WB-D": {"type": "skill", "firstSeenDate": "2025-01-01",
                     "recentDates": ["2025-01-09"], "lastUsedDate": "2025-01-09"},
            "WB-ORPHAN": {"type": "skill", "firstSeenDate": "2025-01-01",
                          "recentDates": ["2025-01-02"], "lastUsedDate": "2025-01-02"},
            "WB-MCP": {"type": "mcp", "firstSeenDate": "2025-01-01",
                       "recentDates": ["2025-01-02"], "lastUsedDate": "2025-01-02"},
        },
    }), encoding="utf-8")
    return root
