"""Cross-ecosystem normalization: merge, provenance attachment, mirror pairing.

The merge layer turns the per-adapter outputs into one deterministic, stable
list of :class:`SkillRecord` (sorted by ``skill_id``), attaches usage and
provenance by skill name, and pairs Hermes/OpenClaw twins as mirrors with a
simple, defensible drift judgement.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, Optional, Sequence

from .model import SkillRecord, SourceEvidence, UsageRecord


def merge_records(record_lists: Iterable[Sequence[SkillRecord]]) -> list[SkillRecord]:
    """Flatten *record_lists*, deduplicate by ``skill_id`` and sort stably."""
    merged: dict[str, SkillRecord] = {}
    for records in record_lists:
        for record in records:
            merged[record.skill_id] = record
    return sorted(merged.values(), key=lambda record: record.skill_id)


def apply_usage_and_provenance(
    records: Sequence[SkillRecord],
    usage_by_ecosystem: Mapping[str, dict[str, UsageRecord]],
    provenance_by_ecosystem: Mapping[str, dict[str, list[SourceEvidence]]],
) -> None:
    """Attach usage and provenance to *records* in place.

    Maps are keyed by ecosystem first, then by skill name, so a Hermes usage
    entry can never leak onto an OpenClaw record that merely shares a name.
    """
    for record in records:
        usage_map = usage_by_ecosystem.get(record.ecosystem, {})
        if record.name in usage_map:
            record.usage = usage_map[record.name]
        provenance_map = provenance_by_ecosystem.get(record.ecosystem, {})
        extra = provenance_map.get(record.name)
        if extra:
            record.provenance.extend(extra)


def _drift(left: SkillRecord, right: SkillRecord) -> str:
    """Judge drift between two mirrored records.

    ``clean`` when both descriptions are present and identical, ``differs`` when
    both are present and differ, ``unknown`` when either is missing.
    """
    if left.description is None or right.description is None:
        return "unknown"
    return "clean" if left.description == right.description else "differs"


def _pick_counterpart(
    group: Sequence[SkillRecord], record: SkillRecord
) -> Optional[SkillRecord]:
    """Choose the mirror counterpart for *record* from its same-name group.

    Same-named records from *other* ecosystems are candidates; an **active**
    counterpart always wins over an archived one, and within the same presence
    class the stable ``skill_id`` order decides. This keeps pairing consistent
    with the mirror view's active-to-active definition.
    """
    others = [other for other in group if other.ecosystem != record.ecosystem]
    if not others:
        return None
    active = [other for other in others if other.presence == "active"]
    pool = active or others
    return min(pool, key=lambda other: other.skill_id)


def pair_mirrors(records: Sequence[SkillRecord]) -> None:
    """Pair same-named skills across ecosystems and record mirror/drift."""
    by_name: dict[str, list[SkillRecord]] = defaultdict(list)
    for record in records:
        by_name[record.name].append(record)

    for group in by_name.values():
        if len(group) < 2:
            continue
        ecosystems = {record.ecosystem for record in group}
        if len(ecosystems) < 2:
            continue
        for record in group:
            counterpart = _pick_counterpart(group, record)
            if counterpart is None:
                continue
            record.mirror_of = counterpart.skill_id
            record.drift = _drift(record, counterpart)
