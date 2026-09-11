"""Structured, container-aware JSONL trajectory parsing (OpenClaw evidence).

OpenClaw has no native skill-usage log, so usage is reconstructed from agent
trajectories. The critical subtlety is that a trajectory embeds *two* very
different things:

* real tool invocations — a message content block carrying
  ``arguments.path`` that points at a ``.../skills/<name>/SKILL.md`` file; and
* a **session snapshot catalog** under ``skills.entries`` — a directory listing
  captured for context, which MUST NEVER be counted as usage.

Only the first is counted in ``use_count`` (the strict caliber). Plain mentions
inside message bodies are recorded separately as corroboration (旁证). This
module implements that split explicitly by tracking the JSON key path during a
depth-first walk.

A malformed line is skipped and reported as a degradation; it never aborts the
scan. ``max_bytes`` (optional) caps how much of each file is read, protecting
against very large trajectories at the cost of completeness.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from ..errors import DegradeReason
from ..logging_setup import Reporter

# A skill path may be nested (``skills/<category>/<name>/SKILL.md``) or flat
# (``skills/<name>/SKILL.md``); the leaf captured is the skill directory name.
SKILL_PATH_RE = re.compile(r"skills/(?:[A-Za-z0-9_.\-]+/)*([A-Za-z0-9_.\-]+)/SKILL\.md")

_EXCLUDED_PATH_PARTS = ("node_modules", "/media/", "/models/", ".git")


@dataclass
class TrajectoryParseResult:
    """Aggregated, deduplicated evidence extracted from trajectory files."""

    strict_use: dict[str, int] = field(default_factory=dict)
    mentions: dict[str, int] = field(default_factory=dict)
    snapshot_names: dict[str, int] = field(default_factory=dict)
    files_scanned: int = 0
    files_truncated: list[str] = field(default_factory=list)
    bad_lines: int = 0
    warnings: list[str] = field(default_factory=list)

    def has_strict_use(self) -> bool:
        return any(count > 0 for count in self.strict_use.values())


def skill_names_in(text: str) -> list[str]:
    """Return every ``<name>`` that appears in a ``skills/<name>/SKILL.md`` path."""
    return SKILL_PATH_RE.findall(text or "")


def iter_trajectory_files(agents_dir: Path) -> list[Path]:
    """Return the trajectory JSONL files found under *agents_dir* (sorted)."""
    base = Path(str(agents_dir))
    found: list[Path] = []
    if not base.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in {"node_modules", "media", "models", ".git"}
        )
        normalized = dirpath.replace("\\", "/")
        if any(part.strip("/") in normalized.split("/") for part in ("media", "models")):
            dirnames[:] = []
            continue
        for filename in filenames:
            lower = filename.lower()
            if lower.endswith(".lock"):
                continue
            if lower.endswith(".jsonl") or "trajectory" in lower:
                found.append(Path(dirpath) / filename)
    found.sort(key=lambda p: p.as_posix())
    return found


# Key-path tokens that mark a *tool-call context*. A SKILL.md-bearing string
# only counts as strict usage when it sits inside such a container — a bare
# ``path`` key anywhere else (config blocks, notes, prose) is never enough.
_TOOL_CALL_TOKENS = frozenset({"arguments", "partialargs", "toolcall", "tool_call", "tool_use"})


def _classify_string(
    key_path: tuple[str, ...],
    in_snapshot: bool,
    value: str,
    result: TrajectoryParseResult,
) -> None:
    """Attribute a SKILL.md-bearing string to the right evidence bucket."""
    names = skill_names_in(value)
    if not names:
        return

    if in_snapshot:
        for name in names:
            result.snapshot_names[name] = result.snapshot_names.get(name, 0) + 1
        return

    tokens = {token.lower() for token in key_path}
    is_tool_args = bool(tokens & _TOOL_CALL_TOKENS)
    if is_tool_args:
        for name in names:
            result.strict_use[name] = result.strict_use.get(name, 0) + 1
        return

    for name in names:
        result.mentions[name] = result.mentions.get(name, 0) + 1


def _walk(
    node: object,
    key_path: tuple[str, ...],
    in_snapshot: bool,
    result: TrajectoryParseResult,
) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_str = str(key)
            child_path = key_path + (key_str,)
            child_snapshot = in_snapshot or (
                len(child_path) >= 2
                and child_path[-1] == "entries"
                and child_path[-2] == "skills"
            )
            if isinstance(value, str):
                if child_snapshot and child_path[-1] == "name":
                    result.snapshot_names[value] = result.snapshot_names.get(value, 0) + 1
                    continue
                _classify_string(child_path, child_snapshot, value, result)
            elif isinstance(value, (dict, list)):
                _walk(value, child_path, child_snapshot, result)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child_path = key_path + (str(index),)
            if isinstance(value, str):
                _classify_string(child_path, in_snapshot, value, result)
            elif isinstance(value, (dict, list)):
                _walk(value, child_path, in_snapshot, result)


def _read_file_lines(path: Path, max_bytes: Optional[int]) -> tuple[list[str], bool]:
    """Return the file's lines and whether it was truncated by *max_bytes*."""
    size = 0
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    truncated = bool(max_bytes and max_bytes > 0 and size > max_bytes)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            data = handle.read(max_bytes) if truncated else handle.read()
    except OSError:
        return [], truncated
    return data.splitlines(), truncated


def parse_trajectory_files(
    files: Iterable[Path],
    *,
    max_bytes: Optional[int] = None,
    reporter: Optional[Reporter] = None,
) -> TrajectoryParseResult:
    """Parse *files* and return aggregated evidence (never raises on bad input)."""
    result = TrajectoryParseResult()
    for path in files:
        result.files_scanned += 1
        lines, truncated = _read_file_lines(Path(str(path)), max_bytes)
        if truncated:
            result.files_truncated.append(Path(str(path)).name)
            message = f"{DegradeReason.TRUNCATED_INPUT}: {Path(str(path)).name} (max_bytes={max_bytes})"
            result.warnings.append(message)
            if reporter is not None:
                reporter.warn(message)
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                # Every JSONL line is expected to be valid JSON; a failure is a
                # degradation, not a crash.
                result.bad_lines += 1
                continue
            _walk(payload, ("root",), False, result)

    if result.bad_lines:
        message = f"{DegradeReason.BAD_JSONL}: {result.bad_lines} malformed line(s) skipped"
        result.warnings.append(message)
        if reporter is not None:
            reporter.warn(message)

    return result
