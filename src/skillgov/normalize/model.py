"""Normalized data model shared by adapters, reports and storage.

Every field is either derived from first-hand read-only evidence or left null —
the model never fabricates timestamps or counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SourceEvidence:
    """One piece of provenance: what was observed and where it came from."""

    kind: str  # store_lock | generated_from | curator | trajectory_mention | birth
    detail: str  # already-safe text
    observed_at: Optional[str] = None  # ISO-8601 UTC

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "detail": self.detail,
            "observed_at": self.observed_at,
        }


@dataclass
class UsageRecord:
    """Aggregated usage for one skill, plus how confident we are about it."""

    use_count: int = 0
    view_count: int = 0
    patch_count: int = 0
    last_used_at: Optional[str] = None
    state: Optional[str] = None
    evidence_source: str = "none"  # usage_json | state_db | trajectory | none
    confidence: str = "C"  # "A" first-hand / "C" inferred

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_count": self.use_count,
            "view_count": self.view_count,
            "patch_count": self.patch_count,
            "last_used_at": self.last_used_at,
            "state": self.state,
            "evidence_source": self.evidence_source,
            "confidence": self.confidence,
        }


@dataclass
class SkillRecord:
    """A single skill, normalized across ecosystems."""

    skill_id: str
    name: str
    ecosystem: str  # hermes | openclaw | workbuddy
    path: str  # relative to the configurable root, never absolute
    presence: str  # active | archived
    category: str  # first path segment under the skills tree
    description: Optional[str] = None
    created_at: Optional[str] = None
    installed_at: Optional[str] = None
    version: Optional[str] = None
    provenance: list[SourceEvidence] = field(default_factory=list)
    usage: UsageRecord = field(default_factory=UsageRecord)
    mirror_of: Optional[str] = None  # counterpart skill_id
    drift: Optional[str] = None  # clean | differs | unknown

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "ecosystem": self.ecosystem,
            "path": self.path,
            "presence": self.presence,
            "category": self.category,
            "description": self.description,
            "created_at": self.created_at,
            "installed_at": self.installed_at,
            "version": self.version,
            "provenance": [item.to_dict() for item in self.provenance],
            "usage": self.usage.to_dict(),
            "mirror_of": self.mirror_of,
            "drift": self.drift,
        }


@dataclass
class RunResult:
    """The outcome of one collection run."""

    records: list[SkillRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    generated_at: str = ""

    def __len__(self) -> int:
        return len(self.records)

    @property
    def degraded(self) -> bool:
        """Whether any degradation or warning was recorded."""
        return bool(self.warnings)
