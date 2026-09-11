"""Hermes ecosystem adapter (read-only).

Discovery walks ``<hermes_root>/skills``. Usage has two possible sources:

* ``skills/.usage.json`` — the curator's per-skill record (authoritative for
  ``patch_count`` / ``state`` and a usable ``use_count``); and
* ``skills/state.db`` — an optional SQLite log whose ``messages`` table records
  ``skill_view`` calls (the more authoritative count when present).

The database is opened strictly read-only and queried defensively
(``json_valid`` guard, column probing), degrading silently when absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import HERMES_SKILLS_SUBPATH, HERMES_STATE_DB_FILENAME, HERMES_USAGE_FILENAME
from ..errors import DegradeReason
from ..logging_setup import Reporter
from ..normalize.model import SkillRecord, SourceEvidence, UsageRecord
from ..readonly import sqlite_ro
from .fs_scan import scan_skills, scanned_to_record


class HermesAdapter:
    """Collect skill records, usage and provenance for a Hermes root."""

    ecosystem = "hermes"

    def __init__(
        self,
        reporter: Optional[Reporter] = None,
        *,
        enable_state_db: bool = True,
        description_limit: int = 200,
    ) -> None:
        self.reporter = reporter if reporter is not None else Reporter()
        self.enable_state_db = enable_state_db
        self.description_limit = description_limit
        self.warnings = self.reporter.warnings

    def capabilities(self) -> set[str]:
        caps = {"discover", "usage", "provenance"}
        if self.enable_state_db:
            caps.add("state_db")
        return caps

    def skills_dir(self, root: Path) -> Path:
        return Path(str(root)) / HERMES_SKILLS_SUBPATH

    def discover(self, root: Path) -> list[SkillRecord]:
        base = self.skills_dir(root)
        if not base.is_dir():
            self.reporter.degrade(DegradeReason.MISSING_SKILLS_DIR, HERMES_SKILLS_SUBPATH)
            return []
        scanned = scan_skills(base, archive_markers=(".archive",))
        return [
            scanned_to_record(
                self.ecosystem,
                HERMES_SKILLS_SUBPATH,
                item,
                description_limit=self.description_limit,
            )
            for item in scanned
        ]

    def usage(self, root: Path) -> dict[str, UsageRecord]:
        base = self.skills_dir(root)
        records: dict[str, UsageRecord] = {}

        usage_path = base / HERMES_USAGE_FILENAME
        if usage_path.is_file():
            records.update(self._usage_from_usage_json(usage_path))
        else:
            self.reporter.degrade(DegradeReason.MISSING_USAGE_JSON, HERMES_USAGE_FILENAME)

        if self.enable_state_db:
            db_path = base / HERMES_STATE_DB_FILENAME
            if db_path.is_file():
                for name, record in self._usage_from_state_db(db_path).items():
                    existing = records.get(name)
                    if existing is None:
                        records[name] = record
                    else:
                        existing.use_count = record.use_count
                        existing.view_count = record.view_count
                        existing.last_used_at = record.last_used_at or existing.last_used_at
                        existing.evidence_source = "state_db"
                        existing.confidence = "A"
            else:
                # Optional capability: a missing state.db degrades *silently*.
                # A present-but-unreadable state.db is reported inside
                # ``_usage_from_state_db`` instead.
                pass
        return records

    def provenance(self, root: Path) -> dict[str, list[SourceEvidence]]:
        base = self.skills_dir(root)
        usage_path = base / HERMES_USAGE_FILENAME
        out: dict[str, list[SourceEvidence]] = {}
        if not usage_path.is_file():
            return out
        try:
            with open(usage_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            self.reporter.degrade(DegradeReason.BAD_JSON, HERMES_USAGE_FILENAME)
            return out
        if not isinstance(data, dict):
            return out
        for name, entry in data.items():
            if not isinstance(entry, dict):
                continue
            detail_parts = [
                f"{key}={entry[key]}"
                for key in ("created_by", "created_at", "archived_at")
                if entry.get(key)
            ]
            if detail_parts:
                out.setdefault(str(name), []).append(
                    SourceEvidence(
                        kind="curator",
                        detail="; ".join(detail_parts),
                        observed_at=entry.get("created_at"),
                    )
                )
        return out

    # -- internals ----------------------------------------------------------
    def _usage_from_usage_json(self, path: Path) -> dict[str, UsageRecord]:
        out: dict[str, UsageRecord] = {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            self.reporter.degrade(DegradeReason.BAD_JSON, path.name)
            return out
        if not isinstance(data, dict):
            self.reporter.degrade(DegradeReason.BAD_JSON, path.name)
            return out
        for name, entry in data.items():
            if not isinstance(entry, dict):
                continue
            out[str(name)] = UsageRecord(
                use_count=int(entry.get("use_count") or 0),
                view_count=int(entry.get("view_count") or 0),
                patch_count=int(entry.get("patch_count") or 0),
                last_used_at=entry.get("last_used_at") or entry.get("last_viewed_at"),
                state=entry.get("state"),
                evidence_source="usage_json",
                confidence="A",
            )
        return out

    def _usage_from_state_db(self, db_path: Path) -> dict[str, UsageRecord]:
        out: dict[str, UsageRecord] = {}
        try:
            connection = sqlite_ro(db_path)
        except (FileNotFoundError, OSError) as exc:
            self.reporter.degrade(DegradeReason.MISSING_STATE_DB, str(exc))
            return out
        try:
            cursor = connection.cursor()
            tables = {
                row[0]
                for row in cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "messages" not in tables:
                self.reporter.degrade(DegradeReason.MISSING_STATE_DB, "no messages table")
                return out
            columns = {row[1] for row in cursor.execute("PRAGMA table_info(messages)")}
            if not {"tool_name", "content"} <= columns:
                self.reporter.degrade(DegradeReason.MISSING_STATE_DB, "missing columns")
                return out
            ts_col = next(
                (col for col in ("timestamp", "ts", "created_at") if col in columns),
                None,
            )
            time_select = (
                f", MIN({ts_col}), MAX({ts_col})" if ts_col else ", NULL, NULL"
            )
            query = (
                "SELECT json_extract(content, '$.name') AS name, COUNT(*) AS n"
                + time_select
                + " FROM messages WHERE tool_name='skill_view' "
                "AND json_valid(content) GROUP BY name"
            )
            for row in cursor.execute(query):
                name = row[0]
                if not name:
                    continue
                out[str(name)] = UsageRecord(
                    use_count=int(row[1]),
                    view_count=int(row[1]),
                    last_used_at=row[3] if ts_col else None,
                    evidence_source="state_db",
                    confidence="A",
                )
        except Exception as exc:  # noqa: BLE001 - degrade, never crash
            self.reporter.degrade(DegradeReason.BAD_JSON, f"state_db:{exc}")
        finally:
            connection.close()
        return out
