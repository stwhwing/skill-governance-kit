"""P0-1: the full inventory view across both ecosystems."""

from __future__ import annotations

from typing import Optional, Sequence

from ..normalize.model import SkillRecord
from .render import base_view, caliber_footer, resolve_include_workbuddy

COLUMNS = [
    "skill_id",
    "name",
    "ecosystem",
    "presence",
    "category",
    "path",
    "created_at",
    "version",
    "description",
    "use_count",
    "evidence_source",
    "mirror_of",
    "drift",
]


def _row(record: SkillRecord) -> list[object]:
    return [
        record.skill_id,
        record.name,
        record.ecosystem,
        record.presence,
        record.category,
        record.path,
        record.created_at,
        record.version,
        record.description,
        record.usage.use_count,
        record.usage.evidence_source,
        record.mirror_of,
        record.drift,
    ]


def build_inventory(
    records: Sequence[SkillRecord],
    *,
    generated_at: str,
    warnings: Sequence[str] = (),
    include_workbuddy_caliber: Optional[bool] = None,
) -> dict[str, object]:
    """Build the inventory view (one row per skill, sorted by ``skill_id``)."""
    ordered = sorted(records, key=lambda record: record.skill_id)
    rows = [_row(record) for record in ordered]

    active = sum(1 for record in ordered if record.presence == "active")
    archived = len(ordered) - active
    by_ecosystem: dict[str, int] = {}
    for record in ordered:
        by_ecosystem[record.ecosystem] = by_ecosystem.get(record.ecosystem, 0) + 1

    include_workbuddy = resolve_include_workbuddy(ordered, include_workbuddy_caliber)
    view = base_view(
        "技能全貌清单 (inventory)",
        generated_at,
        warnings=warnings,
        footer=caliber_footer(include_workbuddy),
    )
    summary: dict[str, object] = {
        "total": len(ordered),
        "active": active,
        "archived": archived,
        "hermes": by_ecosystem.get("hermes", 0),
        "openclaw": by_ecosystem.get("openclaw", 0),
    }
    # Keep v0.1 output byte-identical when WorkBuddy is not part of the run.
    if "workbuddy" in by_ecosystem:
        summary["workbuddy"] = by_ecosystem["workbuddy"]
    view["summary"] = summary
    view["sections"] = [
        {
            "heading": "全量技能清单",
            "type": "table",
            "columns": COLUMNS,
            "rows": rows,
        }
    ]
    return view
