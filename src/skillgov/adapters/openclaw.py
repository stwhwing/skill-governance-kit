"""OpenClaw ecosystem adapter (read-only).

Discovery walks ``<openclaw_root>/workspace/skills``. Because OpenClaw keeps no
native usage log, usage is derived from trajectory files under
``<openclaw_root>/agents`` using the *strict* caliber (only
``messages.content.arguments.path`` counts). The ``skills.entries`` snapshot
catalog is captured separately and never counted.

``.skills_store_lock.json`` supplies installation provenance (source / version /
installedAt).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import (
    OPENCLAW_AGENTS_SUBPATH,
    OPENCLAW_SKILLS_SUBPATH,
    OPENCLAW_STORE_LOCK_FILENAME,
)
from ..errors import DegradeReason
from ..logging_setup import Reporter
from ..normalize.model import SkillRecord, SourceEvidence, UsageRecord
from .fs_scan import scan_skills, scanned_to_record
from .trajectory import (
    TrajectoryParseResult,
    iter_trajectory_files,
    parse_trajectory_files,
)


class OpenClawAdapter:
    """Collect skill records, usage and provenance for an OpenClaw root."""

    ecosystem = "openclaw"

    def __init__(
        self,
        reporter: Optional[Reporter] = None,
        *,
        max_bytes: Optional[int] = None,
        description_limit: int = 200,
    ) -> None:
        self.reporter = reporter if reporter is not None else Reporter()
        self.max_bytes = max_bytes
        self.description_limit = description_limit
        self.warnings = self.reporter.warnings
        self._parse_cache: Optional[TrajectoryParseResult] = None

    def capabilities(self) -> set[str]:
        return {"discover", "usage", "provenance", "trajectory"}

    def skills_dir(self, root: Path) -> Path:
        return Path(str(root)) / OPENCLAW_SKILLS_SUBPATH

    def agents_dir(self, root: Path) -> Path:
        return Path(str(root)) / OPENCLAW_AGENTS_SUBPATH

    def discover(self, root: Path) -> list[SkillRecord]:
        base = self.skills_dir(root)
        if not base.is_dir():
            self.reporter.degrade(
                DegradeReason.MISSING_SKILLS_DIR, OPENCLAW_SKILLS_SUBPATH
            )
            return []
        scanned = scan_skills(base, archive_markers=(".archived",))
        if not scanned:
            self.reporter.degrade(DegradeReason.EMPTY_DIR, OPENCLAW_SKILLS_SUBPATH)
        return [
            scanned_to_record(
                self.ecosystem,
                OPENCLAW_SKILLS_SUBPATH,
                item,
                description_limit=self.description_limit,
            )
            for item in scanned
        ]

    def _parse_agents(self, root: Path) -> TrajectoryParseResult:
        if self._parse_cache is not None:
            return self._parse_cache
        files = iter_trajectory_files(self.agents_dir(root))
        if not files:
            self.reporter.degrade(
                DegradeReason.MISSING_TRAJECTORY, OPENCLAW_AGENTS_SUBPATH
            )
        self._parse_cache = parse_trajectory_files(
            files, max_bytes=self.max_bytes, reporter=self.reporter
        )
        return self._parse_cache

    def usage(self, root: Path) -> dict[str, UsageRecord]:
        parsed = self._parse_agents(root)
        records: dict[str, UsageRecord] = {}
        for name, count in parsed.strict_use.items():
            records[name] = UsageRecord(
                use_count=count,
                view_count=count,
                patch_count=0,
                last_used_at=None,
                evidence_source="trajectory",
                confidence="A" if count > 0 else "C",
            )
        return records

    def provenance(self, root: Path) -> dict[str, list[SourceEvidence]]:
        out: dict[str, list[SourceEvidence]] = {}

        lock_path = self.skills_dir(root) / OPENCLAW_STORE_LOCK_FILENAME
        if lock_path.is_file():
            try:
                with open(lock_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, json.JSONDecodeError):
                self.reporter.degrade(DegradeReason.BAD_JSON, OPENCLAW_STORE_LOCK_FILENAME)
                data = None
            skills = data.get("skills") if isinstance(data, dict) else None
            if isinstance(skills, dict):
                for name, entry in skills.items():
                    if not isinstance(entry, dict):
                        continue
                    detail_parts = []
                    if entry.get("source"):
                        detail_parts.append(f"source={entry['source']}")
                    if entry.get("version"):
                        detail_parts.append(f"version={entry['version']}")
                    if entry.get("installedAt"):
                        detail_parts.append(f"installedAt={entry['installedAt']}")
                    if detail_parts:
                        out.setdefault(str(name), []).append(
                            SourceEvidence(
                                kind="store_lock",
                                detail="; ".join(detail_parts),
                                observed_at=entry.get("installedAt"),
                            )
                        )
        else:
            self.reporter.degrade(
                DegradeReason.MISSING_STORE_LOCK, OPENCLAW_STORE_LOCK_FILENAME
            )

        parsed = self._parse_agents(root)
        for name, count in parsed.mentions.items():
            out.setdefault(name, []).append(
                SourceEvidence(
                    kind="trajectory_mention",
                    detail=(
                        f"message body reference x{count} "
                        "(corroboration only, excluded from use_count)"
                    ),
                    observed_at=None,
                )
            )
        return out
