"""Adapter protocol shared by every ecosystem collector.

Adapters are deliberately small and framework-free: each one only *reads* its
ecosystem's files and returns normalized, evidence-bearing records. Adding a new
ecosystem means implementing this protocol, nothing else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..normalize.model import SkillRecord, SourceEvidence, UsageRecord


@runtime_checkable
class SkillAdapter(Protocol):
    """Structural interface every ecosystem adapter must satisfy."""

    ecosystem: str

    def capabilities(self) -> set[str]:
        """Return the set of advertised capabilities.

        Known values: ``discover``, ``usage``, ``provenance`` and optional
        ecosystem-specific flags such as ``state_db``.
        """
        ...

    def discover(self, root: Path) -> list[SkillRecord]:
        """Return the skill records discovered under *root* (read-only)."""
        ...

    def usage(self, root: Path) -> dict[str, UsageRecord]:
        """Return a ``name -> UsageRecord`` mapping (read-only)."""
        ...

    def provenance(self, root: Path) -> dict[str, list[SourceEvidence]]:
        """Return a ``name -> [SourceEvidence]`` mapping (read-only)."""
        ...
