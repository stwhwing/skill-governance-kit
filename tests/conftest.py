"""Shared pytest fixtures and helpers.

All fixtures are synthetic: skill names use the ``demo-*`` convention, times are
fixed literals and paths are configurable roots (never a real machine path).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def hermes_root() -> Path:
    return FIXTURES_DIR / "hermes-root"


@pytest.fixture
def openclaw_root() -> Path:
    return FIXTURES_DIR / "openclaw-root"


@pytest.fixture
def degenerate_root() -> Path:
    return FIXTURES_DIR / "degenerate"


@pytest.fixture
def make_hermes_state_db(tmp_path):
    """Factory building a minimal, read-only Hermes ``state.db`` fixture."""

    def _make(directory: Path, entries: list[tuple[str, str]]) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        db_path = directory / "state.db"
        connection = sqlite3.connect(str(db_path))
        try:
            connection.execute(
                "CREATE TABLE messages ("
                "id INTEGER PRIMARY KEY, tool_name TEXT, content TEXT, timestamp TEXT)"
            )
            for name, timestamp in entries:
                connection.execute(
                    "INSERT INTO messages (tool_name, content, timestamp) VALUES (?, ?, ?)",
                    ("skill_view", json.dumps({"name": name}), timestamp),
                )
            connection.commit()
        finally:
            connection.close()
        return db_path

    return _make


@pytest.fixture
def hermes_root_with_db(tmp_path, hermes_root, make_hermes_state_db) -> Path:
    """A copied Hermes root enriched with a synthetic ``state.db``."""
    copied = tmp_path / "hermes-root"
    shutil.copytree(str(hermes_root), str(copied))
    make_hermes_state_db(
        copied / "skills",
        [
            ("demo-alpha", "2025-03-01T00:00:00Z"),
            ("demo-alpha", "2025-03-02T00:00:00Z"),
            ("demo-beta", "2025-03-03T00:00:00Z"),
        ],
    )
    return copied
