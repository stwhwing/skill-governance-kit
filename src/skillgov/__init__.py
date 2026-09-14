"""skillgov — a read-only, deterministic skill-governance toolkit.

The package audits AI-agent skill ecosystems (Hermes, OpenClaw and, since
v0.2, WorkBuddy) using a purely read-only pipeline: scan -> normalize ->
report. It never mutates the inspected trees and routes every outward-facing
string through a single redaction gate (:mod:`skillgov.sanitize`).

This module is intentionally lightweight: importing :mod:`skillgov` must not
trigger heavy work or side effects, so that ``python -m skillgov --version``
stays fast and safe.
"""

from __future__ import annotations

__version__ = "0.2.0"
__all__ = ["__version__"]
