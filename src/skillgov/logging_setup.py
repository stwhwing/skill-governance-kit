"""stderr logging / warning conventions for skillgov.

All diagnostics go to stderr so stdout stays free for piped data. Warnings are
collected in a :class:`Reporter` which doubles as the source for
``RunResult.warnings`` (and ultimately the report footer).
"""

from __future__ import annotations

import sys
from typing import Iterable, List

WARN_PREFIX = "WARN"
DEGRADE_PREFIX = "DEGRADE"
ERROR_PREFIX = "ERROR"


def warn(message: str) -> None:
    """Print a ``WARN`` line to stderr."""
    print(f"{WARN_PREFIX}: {message}", file=sys.stderr)


def degrade(reason: str, detail: str = "") -> None:
    """Print a ``DEGRADE`` line to stderr."""
    suffix = f" detail={detail}" if detail else ""
    print(f"{DEGRADE_PREFIX}: reason={reason}{suffix}", file=sys.stderr)


def error(message: str) -> None:
    """Print an ``ERROR`` line to stderr."""
    print(f"{ERROR_PREFIX}: {message}", file=sys.stderr)


class Reporter:
    """Collect warnings (for ``RunResult``) while echoing them to stderr."""

    def __init__(self) -> None:
        self.warnings: List[str] = []

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        warn(message)

    def degrade(self, reason: str, detail: str = "") -> None:
        self.warnings.append(f"{reason}: {detail}" if detail else reason)
        degrade(reason, detail)

    def extend(self, warnings: Iterable[str]) -> None:
        for item in warnings:
            self.warnings.append(item)


class NullReporter(Reporter):
    """Reporter that records warnings silently (used by unit tests)."""

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def degrade(self, reason: str, detail: str = "") -> None:
        self.warnings.append(f"{reason}: {detail}" if detail else reason)
