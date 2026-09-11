"""P0-2 / P0-3: usage view with the zero-usage shortlist and ``--since`` window."""

from __future__ import annotations

from typing import Optional, Sequence

from ..normalize.model import SkillRecord
from .render import base_view

COLUMNS = [
    "skill_id",
    "name",
    "ecosystem",
    "presence",
    "use_count",
    "last_used_at",
    "evidence_source",
    "confidence",
]


def _is_recent(record: SkillRecord, since: Optional[str]) -> bool:
    """Whether *record* counts as "used" within the requested window.

    Without ``since`` a skill is used when ``use_count > 0``. With ``since`` a
    skill counts only when its ``last_used_at`` is present and not earlier than
    the cutoff — so a stale last-use lands it in the zero-usage shortlist.
    """
    if since is None:
        return record.usage.use_count > 0
    last_used = record.usage.last_used_at
    if not last_used:
        return False
    return last_used >= since


def _row(record: SkillRecord) -> list[object]:
    return [
        record.skill_id,
        record.name,
        record.ecosystem,
        record.presence,
        record.usage.use_count,
        record.usage.last_used_at,
        record.usage.evidence_source,
        record.usage.confidence,
    ]


def build_usage(
    records: Sequence[SkillRecord],
    *,
    generated_at: str,
    since: Optional[str] = None,
    warnings: Sequence[str] = (),
) -> dict[str, object]:
    """Build the usage view: a zero-usage shortlist plus the used set."""
    ordered = sorted(records, key=lambda record: record.skill_id)
    used = [record for record in ordered if _is_recent(record, since)]
    zero = [record for record in ordered if not _is_recent(record, since)]

    window = since if since is not None else "all-time"
    view = base_view("技能使用清单 (usage)", generated_at, warnings=warnings)
    view["summary"] = {
        "window": window,
        "total": len(ordered),
        "used": len(used),
        "zero_usage": len(zero),
    }
    view["sections"] = [
        {
            "heading": f"零使用清单 (window={window})",
            "type": "table",
            "columns": COLUMNS,
            "rows": [_row(record) for record in zero],
        },
        {
            "heading": f"已使用清单 (window={window})",
            "type": "table",
            "columns": COLUMNS,
            "rows": [_row(record) for record in used],
        },
    ]
    return view
