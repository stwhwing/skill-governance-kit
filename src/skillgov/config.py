"""Configuration assembly for skillgov.

Resolves the configurable ecosystem roots and provides path helpers. Every
path emitted to reports stays *relative to a configurable root* — machine
specific absolute paths (for example a real home directory) are never carried
into output.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

# Sub-paths relative to a configurable root. These are ecosystem conventions,
# NOT machine-specific locations. Override the root at runtime to relocate.
HERMES_SKILLS_SUBPATH = "skills"
OPENCLAW_SKILLS_SUBPATH = "workspace/skills"
OPENCLAW_AGENTS_SUBPATH = "agents"

# Known auxiliary file names inside a skills tree.
HERMES_USAGE_FILENAME = ".usage.json"
HERMES_STATE_DB_FILENAME = "state.db"
OPENCLAW_STORE_LOCK_FILENAME = ".skills_store_lock.json"

DEFAULT_OUT_DIR = "out"
DEFAULT_DESCRIPTION_LIMIT = 200
DEFAULT_FORMATS: tuple[str, ...] = ("md", "json")

RootLike = Union[str, Path, None]


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with a trailing ``Z``."""
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def normalize_root(value: RootLike) -> Optional[Path]:
    """Turn a user-supplied root into an :class:`~pathlib.Path` (or ``None``)."""
    if value is None or value == "":
        return None
    return Path(str(value)).expanduser()


def relativize(root: RootLike, path: Union[str, Path]) -> str:
    """Express *path* relative to *root* using POSIX separators.

    Falls back to the bare file name when the two share no common ancestor so a
    report never leaks an absolute location.
    """
    p = Path(str(path))
    root_p = normalize_root(root)
    if root_p is not None:
        try:
            return p.resolve().relative_to(root_p.resolve()).as_posix()
        except (ValueError, OSError):
            pass
    return p.name


@dataclass
class Config:
    """Resolved runtime configuration for a single invocation."""

    hermes_root: Optional[Path] = None
    openclaw_root: Optional[Path] = None
    out_dir: Path = field(default_factory=lambda: Path(DEFAULT_OUT_DIR))
    since: Optional[str] = None
    max_bytes: Optional[int] = None
    formats: tuple[str, ...] = DEFAULT_FORMATS
    description_limit: int = DEFAULT_DESCRIPTION_LIMIT
    enable_hermes_state_db: bool = True

    def hermes_skills_dir(self) -> Optional[Path]:
        """Return ``<hermes_root>/skills`` (or ``None`` when unset)."""
        if self.hermes_root is None:
            return None
        return self.hermes_root / HERMES_SKILLS_SUBPATH

    def openclaw_skills_dir(self) -> Optional[Path]:
        """Return ``<openclaw_root>/workspace/skills`` (or ``None``)."""
        if self.openclaw_root is None:
            return None
        return self.openclaw_root / OPENCLAW_SKILLS_SUBPATH

    def openclaw_agents_dir(self) -> Optional[Path]:
        """Return ``<openclaw_root>/agents`` (or ``None``)."""
        if self.openclaw_root is None:
            return None
        return self.openclaw_root / OPENCLAW_AGENTS_SUBPATH
