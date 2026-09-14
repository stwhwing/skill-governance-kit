"""WorkBuddy ecosystem adapter (read-only).

Discovery walks ``<workbuddy_root>/skills`` recursively for ``SKILL.md`` files.
Non-skill auxiliary files (``_*``) and backup directories (``*.bak-*``) are
skipped, and the shared archive markers (``.archive`` / ``*.archived``) mark a
skill as ``archived`` — the same exclusion rules as the other adapters.

Usage comes from the first-hand ledger ``<workbuddy_root>/usage-log.json``::

    {"version": 1,
     "skills": {"<dir-name>": {"type": "skill",
                               "firstSeenDate": "YYYY-MM-DD",
                               "recentDates": ["YYYY-MM-DD", ...],
                               "lastUsedDate": "YYYY-MM-DD"}},
     ...}

Caliber (v0.2): ``use_count`` counts *usage days* (``len(recentDates)``), not
invocation times; ``view_count`` / ``patch_count`` are not tracked by the
ledger and stay ``0``; ``last_used_at`` is ``lastUsedDate`` at midnight UTC.
Ledger keys that match no skill directory are reported as
``orphan_ledger_entry`` warnings and produce no record.

v0.2 scope note: ``audit-log/*.jsonl`` parsing and the ``plugins/cache`` /
``connectors`` trees are intentionally out of scope — the ledger plus the user
skills directory are the only sources consulted.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Optional

from ..config import WORKBUDDY_SKILLS_SUBPATH, WORKBUDDY_USAGE_LOG_FILENAME
from ..errors import DegradeReason
from ..logging_setup import Reporter
from ..normalize.model import SkillRecord, SourceEvidence, UsageRecord
from .fs_scan import ARCHIVE_MARKERS, ScannedSkill, scan_skills, scanned_to_record

# Backup directory segments such as ``wb-demo.bak-20250401`` are never skills.
# Matching is whole-segment: the ``.bak-`` substring must sit inside the segment
# as ``<anything>.bak-<anything>``, so a name like ``sbak-1`` is untouched.
_BAK_SEGMENT_PATTERN = "*.bak-*"

# Archive markers: the single, shared, segment-based set used by all adapters.
WORKBUDDY_ARCHIVE_MARKERS: tuple[str, ...] = ARCHIVE_MARKERS


class WorkBuddyAdapter:
    """Collect skill records, usage and provenance for a WorkBuddy root."""

    ecosystem = "workbuddy"

    def __init__(
        self,
        reporter: Optional[Reporter] = None,
        *,
        description_limit: int = 200,
    ) -> None:
        self.reporter = reporter if reporter is not None else Reporter()
        self.description_limit = description_limit
        self.warnings = self.reporter.warnings
        # Per-root caches so usage()/provenance() never duplicate degrade
        # warnings (or orphan warnings) for the same ledger within one run.
        self._ledger_cache: dict[str, Optional[dict]] = {}
        self._ledger_index_cache: dict[str, dict[str, dict]] = {}
        self._dir_names_cache: dict[str, set[str]] = {}

    def capabilities(self) -> set[str]:
        return {"discover", "usage", "provenance", "usage_log"}

    def skills_dir(self, root: Path) -> Path:
        return Path(str(root)) / WORKBUDDY_SKILLS_SUBPATH

    def usage_log_path(self, root: Path) -> Path:
        return Path(str(root)) / WORKBUDDY_USAGE_LOG_FILENAME

    # -- filtering ----------------------------------------------------------
    @staticmethod
    def _is_skipped_segment(segment: str) -> bool:
        """Whether a *whole* path segment can never contain a real skill.

        Two documented rules, both segment-anchored:
        * the segment starts with ``_`` (auxiliary files such as
          ``_bm_skillid_migration.json`` live under such directories); or
        * the segment matches ``*.bak-*`` (backup copies).
        """
        if segment.startswith("_"):
            return True
        return fnmatch.fnmatchcase(segment, _BAK_SEGMENT_PATTERN)

    def _visible(self, scanned: list[ScannedSkill]) -> list[ScannedSkill]:
        """Drop skills living under ``_*`` or ``*.bak-*`` segments."""
        return [
            item
            for item in scanned
            if not any(self._is_skipped_segment(seg) for seg in item.rel_dir.split("/"))
        ]

    def _scan_visible(self, root: Path) -> list[ScannedSkill]:
        base = self.skills_dir(root)
        if not base.is_dir():
            return []
        return self._visible(
            scan_skills(base, archive_markers=WORKBUDDY_ARCHIVE_MARKERS)
        )

    def _skill_dir_names(self, root: Path) -> set[str]:
        """Directory names of every visible skill (ledger keys match these)."""
        cached = self._dir_names_cache.get(str(root))
        if cached is not None:
            return cached
        names = {
            item.rel_dir.split("/")[-1] for item in self._scan_visible(root) if item.rel_dir
        }
        self._dir_names_cache[str(root)] = names
        return names

    # -- protocol -----------------------------------------------------------
    def discover(self, root: Path) -> list[SkillRecord]:
        base = self.skills_dir(root)
        if not base.is_dir():
            self.reporter.degrade(
                DegradeReason.MISSING_SKILLS_DIR, WORKBUDDY_SKILLS_SUBPATH
            )
            return []
        visible = self._scan_visible(root)
        if not visible:
            self.reporter.degrade(DegradeReason.EMPTY_DIR, WORKBUDDY_SKILLS_SUBPATH)
        return [
            scanned_to_record(
                self.ecosystem,
                WORKBUDDY_SKILLS_SUBPATH,
                item,
                description_limit=self.description_limit,
            )
            for item in visible
        ]

    def usage(self, root: Path) -> dict[str, UsageRecord]:
        index = self._skill_ledger(root)
        records: dict[str, UsageRecord] = {}
        for key, entry in index.items():
            recent = entry.get("recentDates")
            use_days = len(recent) if isinstance(recent, list) else 0
            records[key] = UsageRecord(
                use_count=use_days,
                view_count=0,
                patch_count=0,
                last_used_at=self._last_used_at(entry),
                state=None,
                evidence_source="usage_log",
                confidence="A",
            )
        return records

    def provenance(self, root: Path) -> dict[str, list[SourceEvidence]]:
        # Reuses the *same* filtered index as :meth:`usage`, so a
        # ``type != "skill"`` entry or an orphan ledger key can never attach
        # ``usage_log`` evidence to a skill whose ``usage.evidence_source``
        # remains ``none`` (evidence and usage must never contradict).
        index = self._skill_ledger(root)
        out: dict[str, list[SourceEvidence]] = {}
        for key, entry in index.items():
            out[key] = [
                SourceEvidence(
                    kind="usage_log",
                    detail=f"workbuddy {WORKBUDDY_USAGE_LOG_FILENAME}",
                    observed_at=self._last_used_date(entry),
                )
            ]
        return out

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _last_used_date(entry: dict) -> Optional[str]:
        """The raw ``lastUsedDate`` string (or ``None``)."""
        value = entry.get("lastUsedDate")
        return str(value) if isinstance(value, str) and value else None

    @staticmethod
    def _last_used_at(entry: dict) -> Optional[str]:
        """``lastUsedDate`` normalized to midnight UTC ISO-8601."""
        date = WorkBuddyAdapter._last_used_date(entry)
        return f"{date}T00:00:00Z" if date else None

    def _skill_ledger(self, root: Path) -> dict[str, dict]:
        """The ledger entries that correspond to a real skill, keyed by name.

        This is the *single* shared mapping behind both :meth:`usage` and
        :meth:`provenance` — filtering happens exactly once (and the
        ``orphan_ledger_entry`` warning is therefore emitted exactly once per
        root, even when both methods run in one pass).
        """
        cached = self._ledger_index_cache.get(str(root))
        if cached is not None:
            return cached
        index: dict[str, dict] = {}
        ledger = self._ledger(root)
        if ledger:
            dir_names = self._skill_dir_names(root)
            for key in sorted(ledger):
                entry = ledger[key]
                if not isinstance(entry, dict):
                    continue
                entry_type = entry.get("type")
                if entry_type is not None and entry_type != "skill":
                    # e.g. an ``mcps`` entry: never a skill usage record.
                    continue
                if key not in dir_names:
                    # Ledger key with no matching skill directory: warn, never
                    # fabricate a record for a ghost skill.
                    self.reporter.warn(f"orphan_ledger_entry: {key}")
                    continue
                index[str(key)] = entry
        self._ledger_index_cache[str(root)] = index
        return index

    def _ledger(self, root: Path) -> Optional[dict]:
        """Load (and cache) the ``skills`` ledger; ``None`` when unusable."""
        cached = self._ledger_cache.get(str(root))
        if cached is not None:
            return cached
        if str(root) in self._ledger_cache:
            return None  # cached as unusable
        ledger = self._load_ledger(root)
        self._ledger_cache[str(root)] = ledger if ledger else None
        return self._ledger_cache[str(root)]

    def _load_ledger(self, root: Path) -> Optional[dict]:
        path = self.usage_log_path(root)
        if not path.is_file():
            self.reporter.degrade(
                DegradeReason.MISSING_USAGE_JSON, WORKBUDDY_USAGE_LOG_FILENAME
            )
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            self.reporter.degrade(DegradeReason.BAD_JSON, WORKBUDDY_USAGE_LOG_FILENAME)
            return None
        if not isinstance(data, dict):
            self.reporter.degrade(DegradeReason.BAD_JSON, WORKBUDDY_USAGE_LOG_FILENAME)
            return None
        skills = data.get("skills")
        if skills is None:
            skills = {}
        if not isinstance(skills, dict):
            self.reporter.degrade(DegradeReason.BAD_JSON, WORKBUDDY_USAGE_LOG_FILENAME)
            return None
        if not skills:
            self.reporter.degrade(
                DegradeReason.EMPTY_USAGE_LOG, WORKBUDDY_USAGE_LOG_FILENAME
            )
            return {}
        return skills
