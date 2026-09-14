#!/usr/bin/env python3
"""Regenerate ``examples/out/**`` reproducibly on any operating system.

The committed example snapshots must be byte-identical no matter who
regenerates them or on which OS. A raw CLI run is *not* reproducible because of
the two environment-dependent fields documented in
:mod:`skillgov.determinism`:

* ``created_at`` — a best-effort file creation time (``None`` on POSIX without
  ``st_birthtime``, a checkout timestamp on Windows);
* ``generated_at`` — the wall-clock time of the run.

This script runs the *real* CLI pipeline over the committed fixtures under
``tests/fixtures/**`` and then rewrites every artifact through
:func:`skillgov.determinism.normalize_env_dependent`:

* ``records.json`` keeps every field but normalises each ``created_at`` to
  ``null``;
* every view ``*.json`` is stored with ``created_at`` nulled and
  ``generated_at`` removed, and its ``*.md`` sibling is rendered from that exact
  normalised view (so the two representations can never drift apart).

Result: running this script anywhere produces the exact same ``examples/out/**``.
Usage::

    python scripts/regen_examples.py

It only writes to ``examples/out/**`` (plus a scratch directory under the system
temporary directory) and has no runtime dependencies beyond the standard
library.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skillgov.cli.main import main as cli_main  # noqa: E402
from skillgov.determinism import (  # noqa: E402
    DROP,
    find_env_dependent,
    normalize_env_dependent,
)
from skillgov.report.render import render_view  # noqa: E402
from skillgov.store.json_store import (  # noqa: E402
    dumps_stable,
    write_text_atomic,
)

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
HERMES_ROOT = FIXTURES_DIR / "hermes-root"
OPENCLAW_ROOT = FIXTURES_DIR / "openclaw-root"
EXAMPLES_OUT = REPO_ROOT / "examples" / "out"

CARD_SKILL_ID = "hermes:demo-alpha"
REPORT_SINCE = "2025-01-01"
VIEW_NAMES = ("inventory", "usage", "mirror", "report")


def _pipeline_runs() -> list[list[str]]:
    """The CLI invocations that reproduce ``examples/out/**`` exactly.

    Order matters: the ``report`` bundle writes a windowed ``usage`` view, then
    a dedicated all-time ``usage`` run overwrites it (``examples/out/usage.*``
    is the all-time window), and a single ``card`` run adds the archive card.
    """
    roots = ["--hermes-root", str(HERMES_ROOT), "--openclaw-root", str(OPENCLAW_ROOT)]
    return [
        ["report", *roots, "--since", REPORT_SINCE],
        ["usage", *roots],
        ["card", CARD_SKILL_ID, *roots],
    ]


def _run_pipeline(work_dir: Path) -> None:
    """Run every pipeline invocation into *work_dir*."""
    for command in _pipeline_runs():
        code = cli_main([*command, "--out", str(work_dir), "--format", "md,json"])
        if code != 0:
            raise SystemExit(
                f"pipeline command failed (exit {code}): {' '.join(command)}"
            )


def _normalized_artifacts(work_dir: Path) -> dict[str, str]:
    """Return ``{filename: text}`` for the fully normalised example snapshots."""
    artifacts: dict[str, str] = {}
    for path in sorted(work_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name == "records.json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            normalized = normalize_env_dependent(payload)
            artifacts[path.name] = dumps_stable(normalized) + "\n"
            continue
        if path.suffix == ".json":
            view = json.loads(path.read_text(encoding="utf-8"))
            normalized = normalize_env_dependent(view, generated_at=DROP)
            artifacts[path.name] = dumps_stable(normalized) + "\n"
            artifacts[path.with_suffix(".md").name] = render_view(normalized, "md")
    return artifacts


def _prune_stale(keep: set[str]) -> list[Path]:
    """Delete committed files under ``examples/out`` not in *keep*."""
    removed: list[Path] = []
    if not EXAMPLES_OUT.is_dir():
        return removed
    for existing in sorted(EXAMPLES_OUT.iterdir()):
        if existing.is_file() and existing.name not in keep:
            existing.unlink()
            removed.append(existing)
    return removed


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _verify(paths: list[Path]) -> list[str]:
    """Return a list of integrity problems for the written snapshots."""
    problems: list[str] = []
    for path in paths:
        if path.suffix != ".json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        leaks = find_env_dependent(payload)
        if leaks:
            problems.append(f"{path.name}: env-dependent values {leaks}")
    for view in VIEW_NAMES:
        view_path = EXAMPLES_OUT / f"{view}.json"
        markdown_path = EXAMPLES_OUT / f"{view}.md"
        if not view_path.is_file() or not markdown_path.is_file():
            continue
        view = json.loads(view_path.read_text(encoding="utf-8"))
        if markdown_path.read_text(encoding="utf-8") != render_view(view, "md"):
            problems.append(f"{view}.md does not match its normalised {view}.json")
    return problems


def regenerate() -> list[Path]:
    """Regenerate ``examples/out/**`` deterministically and return the paths."""
    EXAMPLES_OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skillgov-examples-") as tmp:
        work_dir = Path(tmp)
        _run_pipeline(work_dir)
        artifacts = _normalized_artifacts(work_dir)

    removed = _prune_stale(set(artifacts))

    written: list[Path] = []
    for name in sorted(artifacts):
        written.append(write_text_atomic(EXAMPLES_OUT / name, artifacts[name]))

    print(f"Regenerated {len(written)} file(s) under {EXAMPLES_OUT}:")
    for path in written:
        print(f"  {path.name}  sha256={_sha256(path.read_text(encoding='utf-8'))}")
    if removed:
        print("Removed stale file(s):")
        for path in removed:
            print(f"  {path.name}")

    problems = _verify(written)
    if problems:
        for problem in problems:
            print(f"VERIFY FAILED: {problem}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"Verified: all {len(written)} snapshot(s) are environment-free "
        "(created_at=null, no generated_at) and md/json are consistent."
    )
    return written


if __name__ == "__main__":
    regenerate()
