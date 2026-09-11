"""P1-1: the dual-ecosystem mirror comparison view."""

from __future__ import annotations

from typing import Sequence

from ..normalize.model import SkillRecord
from .render import base_view

COLUMNS = ["name", "hermes_skill_id", "openclaw_skill_id", "drift"]


def build_mirror(
    records: Sequence[SkillRecord],
    *,
    generated_at: str,
    warnings: Sequence[str] = (),
) -> dict[str, object]:
    """Build the mirror view listing every cross-ecosystem twin pair."""
    by_name: dict[str, dict[str, SkillRecord]] = {}
    for record in sorted(records, key=lambda item: item.skill_id):
        by_name.setdefault(record.name, {})[record.ecosystem] = record

    pairs: list[list[object]] = []
    clean = differs = unknown = 0
    for name in sorted(by_name):
        group = by_name[name]
        if "hermes" not in group or "openclaw" not in group:
            continue
        hermes = group["hermes"]
        openclaw = group["openclaw"]
        drift = hermes.drift or openclaw.drift or "unknown"
        if drift == "clean":
            clean += 1
        elif drift == "differs":
            differs += 1
        else:
            unknown += 1
        pairs.append([name, hermes.skill_id, openclaw.skill_id, drift])

    view = base_view("双生态镜像对照 (mirror)", generated_at, warnings=warnings)
    view["summary"] = {
        "pairs": len(pairs),
        "clean": clean,
        "differs": differs,
        "unknown": unknown,
    }
    view["sections"] = [
        {
            "heading": "镜像对（同名跨生态）",
            "type": "table",
            "columns": COLUMNS,
            "rows": pairs,
        }
    ]
    return view
