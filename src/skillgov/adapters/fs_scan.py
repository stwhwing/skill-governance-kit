"""Filesystem scan adapter: SKILL.md discovery, frontmatter, stat, archiving.

This is the shared discovery core for both ecosystems. It walks a skills tree,
finds every ``SKILL.md``, parses its YAML-ish frontmatter with a *line based*
parser (no PyYAML, keeping the runtime dependency-free), records a birth
timestamp where the platform exposes one, and classifies the skill as
``active`` or ``archived`` based on configurable path markers.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from ..normalize.model import SkillRecord, SourceEvidence
from ..store.ids import make_skill_id

SKILL_FILENAME = "SKILL.md"
EXCLUDED_DIR_NAMES = frozenset({"node_modules", "__pycache__", ".git", ".hg", ".svn"})
DEFAULT_ARCHIVE_MARKERS: tuple[str, ...] = (".archive", ".archived")

_GENERATED_FROM_RE = re.compile(
    r"generated[_-]?from['\"]?\s*[:=]\s*['\"]?([^\n\"']+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScannedSkill:
    """A single ``SKILL.md`` found on disk, before normalization."""

    rel_dir: str
    name: str
    category: str
    presence: str
    description: Optional[str]
    version: Optional[str]
    generated_from: Optional[str]
    created_at: Optional[str]


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse a leading ``---`` frontmatter block into a flat mapping.

    Only simple ``key: value`` pairs are understood; nested structures are out
    of scope. This mirrors the behaviour of the reference probes and avoids a
    PyYAML dependency.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    block = text[3:end] if end > 0 else text[3:3000]
    frontmatter: dict[str, str] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip().strip("\"'").strip()
        if key and value:
            frontmatter[key] = value
    return frontmatter


def _epoch_to_iso(timestamp: Optional[float]) -> Optional[str]:
    """Convert a POSIX timestamp to an ISO-8601 UTC string (or ``None``)."""
    if timestamp is None:
        return None
    try:
        return (
            _dt.datetime.fromtimestamp(float(timestamp), _dt.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError):
        return None


def _birth_time(stat_result: os.stat_result) -> Optional[str]:
    """Best-effort file creation time (Windows: ``st_ctime``)."""
    birth = getattr(stat_result, "st_birthtime", None)
    if birth is None and os.name == "nt":
        birth = getattr(stat_result, "st_ctime", None)
    return _epoch_to_iso(birth)


def _read_head(path: Path, limit: int = 60000) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def scan_skills(
    skills_dir: Iterable[Path] | Path,
    *,
    archive_markers: tuple[str, ...] = DEFAULT_ARCHIVE_MARKERS,
) -> list[ScannedSkill]:
    """Discover every ``SKILL.md`` under *skills_dir*.

    The result is sorted by relative directory so callers get a deterministic
    order regardless of filesystem enumeration quirks.
    """
    base = Path(str(skills_dir))
    results: list[ScannedSkill] = []
    if not base.is_dir():
        return results

    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIR_NAMES)
        if SKILL_FILENAME not in filenames:
            continue

        md_path = Path(dirpath) / SKILL_FILENAME
        try:
            rel_dir = Path(dirpath).relative_to(base).as_posix()
        except ValueError:
            rel_dir = Path(dirpath).name
        if rel_dir == ".":
            rel_dir = ""

        text = _read_head(md_path)
        frontmatter = parse_frontmatter(text)
        name = (frontmatter.get("name") or Path(dirpath).name).strip()

        category = rel_dir.split("/")[0] if rel_dir else "(root)"
        presence = (
            "archived"
            if any(marker in rel_dir for marker in archive_markers)
            else "active"
        )

        generated_from = frontmatter.get("generated_from") or frontmatter.get(
            "generated-from"
        )
        if not generated_from:
            match = _GENERATED_FROM_RE.search(text)
            if match:
                generated_from = match.group(1).strip()

        description = frontmatter.get("description") or frontmatter.get("summary")
        version = frontmatter.get("version")

        created_at: Optional[str] = None
        try:
            created_at = _birth_time(md_path.stat())
        except OSError:
            created_at = None

        results.append(
            ScannedSkill(
                rel_dir=rel_dir,
                name=name,
                category=category,
                presence=presence,
                description=description,
                version=version,
                generated_from=generated_from,
                created_at=created_at,
            )
        )

    results.sort(key=lambda item: item.rel_dir)
    return results


def scanned_to_record(
    ecosystem: str,
    skills_subpath: str,
    scanned: ScannedSkill,
    *,
    description_limit: int,
) -> SkillRecord:
    """Convert a :class:`ScannedSkill` into a normalized :class:`SkillRecord`."""
    rel_dir = scanned.rel_dir
    rel_to_root = f"{skills_subpath}/{rel_dir}".rstrip("/") if rel_dir else skills_subpath

    description = scanned.description
    if description is not None and description_limit > 0 and len(description) > description_limit:
        description = description[:description_limit]

    provenance: list[SourceEvidence] = []
    if scanned.generated_from:
        provenance.append(
            SourceEvidence(
                kind="generated_from",
                detail=scanned.generated_from,
                observed_at=scanned.created_at,
            )
        )

    return SkillRecord(
        skill_id=make_skill_id(ecosystem, rel_dir),
        name=scanned.name,
        ecosystem=ecosystem,
        path=rel_to_root,
        presence=scanned.presence,
        category=scanned.category,
        description=description,
        created_at=scanned.created_at,
        version=scanned.version,
        provenance=provenance,
    )
