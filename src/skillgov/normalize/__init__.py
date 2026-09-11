"""Normalization: the shared data model and cross-ecosystem merge logic."""

from __future__ import annotations

from .merge import (
    apply_usage_and_provenance,
    merge_records,
    pair_mirrors,
)
from .model import RunResult, SkillRecord, SourceEvidence, UsageRecord

__all__ = [
    "RunResult",
    "SkillRecord",
    "SourceEvidence",
    "UsageRecord",
    "merge_records",
    "apply_usage_and_provenance",
    "pair_mirrors",
]
