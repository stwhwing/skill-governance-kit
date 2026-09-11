"""P0-5: a per-skill provenance and evolution archive card."""

from __future__ import annotations

from typing import Optional, Sequence

from ..normalize.model import SkillRecord
from .render import base_view


def find_record(
    records: Sequence[SkillRecord], skill_id: str
) -> Optional[SkillRecord]:
    """Return the record whose ``skill_id`` matches exactly (or ``None``)."""
    for record in records:
        if record.skill_id == skill_id:
            return record
    return None


def build_card(
    records: Sequence[SkillRecord],
    skill_id: str,
    *,
    generated_at: str,
    warnings: Sequence[str] = (),
) -> dict[str, object]:
    """Build a single-skill card view; ``sections`` stays empty when not found."""
    record = find_record(records, skill_id)
    view = base_view(f"技能档案卡 (card): {skill_id}", generated_at, warnings=warnings)
    if record is None:
        view["summary"] = {"found": False, "skill_id": skill_id}
        view["sections"] = [
            {
                "heading": "结果",
                "type": "text",
                "text": f"未找到 skill_id={skill_id}。",
            }
        ]
        return view

    view["summary"] = {"found": True, "skill_id": record.skill_id}
    identity = [
        ["name", record.name],
        ["ecosystem", record.ecosystem],
        ["presence", record.presence],
        ["category", record.category],
        ["path", record.path],
        ["version", record.version],
        ["created_at", record.created_at],
        ["installed_at", record.installed_at],
        ["description", record.description],
        ["mirror_of", record.mirror_of],
        ["drift", record.drift],
    ]
    usage = [
        ["use_count", record.usage.use_count],
        ["view_count", record.usage.view_count],
        ["patch_count", record.usage.patch_count],
        ["last_used_at", record.usage.last_used_at],
        ["state", record.usage.state],
        ["evidence_source", record.usage.evidence_source],
        ["confidence", record.usage.confidence],
    ]
    provenance = [
        [evidence.kind, f"{evidence.detail} @ {evidence.observed_at or '-'}"]
        for evidence in record.provenance
    ]
    view["sections"] = [
        {"heading": "身份", "type": "kv", "items": identity},
        {"heading": "使用", "type": "kv", "items": usage},
        {"heading": "来源证据 (provenance)", "type": "table",
         "columns": ["kind", "detail"], "rows": provenance},
    ]
    return view
