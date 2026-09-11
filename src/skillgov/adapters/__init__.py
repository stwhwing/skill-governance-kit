"""Read-only collection adapters, one per skill ecosystem."""

from __future__ import annotations

from .base import SkillAdapter
from .fs_scan import scan_skills
from .hermes import HermesAdapter
from .openclaw import OpenClawAdapter

__all__ = ["SkillAdapter", "scan_skills", "HermesAdapter", "OpenClawAdapter"]
