"""argparse dispatch, the collection pipeline and exit-code handling.

Subcommands: ``inventory`` | ``usage`` | ``card`` | ``mirror`` | ``report``.

Exit codes (see design section 4):

===  =========================================================
0    success (including a run that degraded *with a reason*)
1    unexpected internal error
2    CLI argument error (argparse or an invalid option value)
3    no usable data source at all
===  =========================================================
"""

from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path
from typing import Optional, Sequence

from .. import __version__
from ..config import (
    DEFAULT_DESCRIPTION_LIMIT,
    DEFAULT_FORMATS,
    DEFAULT_OUT_DIR,
    Config,
    normalize_root,
    utc_now_iso,
)
from ..errors import (
    EXIT_CLI,
    EXIT_INTERNAL,
    EXIT_NO_SOURCE,
    EXIT_OK,
    ConfigError,
    DegradeReason,
    SkillgovError,
)
from ..logging_setup import Reporter, error
from ..normalize.model import RunResult
from ..normalize.merge import apply_usage_and_provenance, merge_records, pair_mirrors
from ..readonly import assert_no_writes, snapshot_tree
from ..report.card import build_card
from ..report.inventory import build_inventory
from ..report.mirror import build_mirror
from ..report.render import write_view
from ..report.usage import build_usage
from ..sanitize import sanitize, sanitize_obj
from ..store.ids import make_skill_id, rel_path_slug, slug_safe
from ..store.json_store import write_json_atomic
from ..adapters.hermes import HermesAdapter
from ..adapters.openclaw import OpenClawAdapter
from ..adapters.workbuddy import WorkBuddyAdapter

SUBCOMMANDS = ("inventory", "usage", "card", "mirror", "report")


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser and its subparsers."""
    parser = argparse.ArgumentParser(
        prog="skillgov",
        description=(
            "Read-only, deterministic skill-governance toolkit for "
            "Hermes, OpenClaw and WorkBuddy."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"skillgov {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(target: argparse.ArgumentParser) -> None:
        target.add_argument("--hermes-root", default=None, help="Hermes root (contains skills/)")
        target.add_argument(
            "--openclaw-root", default=None, help="OpenClaw root (contains workspace/skills, agents/)"
        )
        target.add_argument(
            "--workbuddy-root", default=None, help="WorkBuddy root (contains skills/, usage-log.json)"
        )
        target.add_argument("--out", default=DEFAULT_OUT_DIR, help="output directory")
        target.add_argument(
            "--format", default=",".join(DEFAULT_FORMATS), help="comma list: md,json"
        )
        target.add_argument(
            "--assert-readonly",
            action="store_true",
            default=False,
            help="snapshot every configured root before/after the run; fail (exit 1) on any change",
        )

    inventory = subparsers.add_parser("inventory", help="full skill inventory")
    add_common(inventory)

    usage = subparsers.add_parser("usage", help="usage / zero-usage shortlist")
    add_common(usage)
    usage.add_argument("--since", default=None, help="ISO date, e.g. 2025-01-01")

    card = subparsers.add_parser("card", help="single-skill archive card")
    add_common(card)
    card.add_argument("skill_id", help="skill id, e.g. hermes:demo-alpha")

    mirror = subparsers.add_parser("mirror", help="cross-ecosystem mirror comparison")
    add_common(mirror)

    report = subparsers.add_parser("report", help="full report bundle")
    add_common(report)
    report.add_argument("--since", default=None, help="ISO date window for usage")
    report.add_argument(
        "--max-bytes", type=int, default=None, help="cap bytes read per trajectory file"
    )
    return parser


def _parse_formats(value: str) -> tuple[str, ...]:
    """Parse and validate the ``--format`` option."""
    formats = tuple(item.strip().lower() for item in str(value).split(",") if item.strip())
    if not formats:
        raise ConfigError("--format must list at least one of: md,json")
    invalid = [fmt for fmt in formats if fmt not in ("md", "json")]
    if invalid:
        raise ConfigError(f"unsupported --format value(s): {', '.join(invalid)}")
    return formats


def _build_config(args: argparse.Namespace) -> Config:
    """Translate parsed CLI arguments into a :class:`Config`."""
    formats = _parse_formats(getattr(args, "format", ",".join(DEFAULT_FORMATS)))
    since = getattr(args, "since", None)
    if since is not None:
        try:
            _dt.date.fromisoformat(str(since))
        except ValueError as exc:
            raise ConfigError("--since must be an ISO date, e.g. 2025-01-01") from exc
    max_bytes = getattr(args, "max_bytes", None)
    if max_bytes is not None and max_bytes <= 0:
        raise ConfigError("--max-bytes must be a positive integer")
    out_dir = Path(str(getattr(args, "out", DEFAULT_OUT_DIR)))
    if out_dir.exists() and not out_dir.is_dir():
        raise ConfigError(f"--out must be a directory, but an existing file is in the way: {out_dir}")
    return Config(
        hermes_root=normalize_root(getattr(args, "hermes_root", None)),
        openclaw_root=normalize_root(getattr(args, "openclaw_root", None)),
        workbuddy_root=normalize_root(getattr(args, "workbuddy_root", None)),
        out_dir=out_dir,
        since=since,
        max_bytes=max_bytes,
        formats=formats,
        description_limit=DEFAULT_DESCRIPTION_LIMIT,
        assert_readonly=bool(getattr(args, "assert_readonly", False)),
    )


def _resolve_skill_id(requested: str) -> str:
    """Normalize a user-supplied ``skill_id`` through the redaction gate.

    Lookup happens on the sanitized, slugified form so an id typed before
    redaction (for example one embedding an address) resolves to the same
    stable record while never re-entering reports verbatim.
    """
    text = sanitize(str(requested)).strip()
    if ":" in text:
        ecosystem, _, rest = text.partition(":")
        return make_skill_id(ecosystem, rest)
    return rel_path_slug(text)


def collect(config: Config, reporter: Reporter) -> RunResult:
    """Run the read-only collection pipeline and return a :class:`RunResult`.

    When ``config.assert_readonly`` is set, every configured root is snapshotted
    before and after the run; any difference raises
    :class:`~skillgov.errors.ReadOnlyViolation` (an internal error -> exit 1).
    """
    guarded_roots = [
        root
        for root in (config.hermes_root, config.openclaw_root, config.workbuddy_root)
        if root is not None
    ]
    before_snapshots = (
        [snapshot_tree(root) for root in guarded_roots]
        if config.assert_readonly
        else []
    )

    records = []
    usage_by_ecosystem: dict[str, dict] = {}
    provenance_by_ecosystem: dict[str, dict] = {}
    sources: list[str] = []

    if config.hermes_root is not None:
        if config.hermes_skills_dir() is not None and config.hermes_skills_dir().is_dir():
            adapter = HermesAdapter(
                reporter,
                enable_state_db=config.enable_hermes_state_db,
                description_limit=config.description_limit,
            )
            records.extend(adapter.discover(config.hermes_root))
            usage_by_ecosystem["hermes"] = adapter.usage(config.hermes_root)
            provenance_by_ecosystem["hermes"] = adapter.provenance(config.hermes_root)
            sources.append("hermes")
        else:
            reporter.degrade(DegradeReason.MISSING_SKILLS_DIR, "hermes")
    else:
        reporter.degrade(DegradeReason.MISSING_ROOT, "hermes")

    if config.openclaw_root is not None:
        if config.openclaw_skills_dir() is not None and config.openclaw_skills_dir().is_dir():
            adapter = OpenClawAdapter(
                reporter,
                max_bytes=config.max_bytes,
                description_limit=config.description_limit,
            )
            records.extend(adapter.discover(config.openclaw_root))
            usage_by_ecosystem["openclaw"] = adapter.usage(config.openclaw_root)
            provenance_by_ecosystem["openclaw"] = adapter.provenance(config.openclaw_root)
            sources.append("openclaw")
        else:
            reporter.degrade(DegradeReason.MISSING_SKILLS_DIR, "openclaw")
    else:
        reporter.degrade(DegradeReason.MISSING_ROOT, "openclaw")

    # WorkBuddy (v0.2) is opt-in: an absent --workbuddy-root keeps the run
    # byte-identical to v0.1 (no extra degrade warning), while a provided root
    # degrades exactly like the other ecosystems when its tree is unusable.
    if config.workbuddy_root is not None:
        if config.workbuddy_skills_dir() is not None and config.workbuddy_skills_dir().is_dir():
            adapter = WorkBuddyAdapter(
                reporter,
                description_limit=config.description_limit,
            )
            records.extend(adapter.discover(config.workbuddy_root))
            usage_by_ecosystem["workbuddy"] = adapter.usage(config.workbuddy_root)
            provenance_by_ecosystem["workbuddy"] = adapter.provenance(config.workbuddy_root)
            sources.append("workbuddy")
        else:
            reporter.degrade(DegradeReason.MISSING_SKILLS_DIR, "workbuddy")

    merged = merge_records([records])
    apply_usage_and_provenance(merged, usage_by_ecosystem, provenance_by_ecosystem)
    pair_mirrors(merged)

    if config.assert_readonly:
        for root, before in zip(guarded_roots, before_snapshots):
            assert_no_writes(before, snapshot_tree(root))

    return RunResult(
        records=merged,
        warnings=list(reporter.warnings),
        sources=sources,
        generated_at=utc_now_iso(),
    )


def _write_command_outputs(
    args: argparse.Namespace, config: Config, result: RunResult
) -> int:
    """Build and write the view(s) for the requested subcommand."""
    command = args.command
    warnings = result.warnings
    # The WorkBuddy caliber line is injected only when the run actually covers
    # the WorkBuddy ecosystem, so a Hermes+OpenClaw-only run stays byte-identical
    # to v0.1 (spec E). ``sources`` is authoritative and reflects *coverage*:
    # "workbuddy" is appended only when <workbuddy-root>/skills exists, so a
    # present-but-empty tree still counts while a root whose ``skills``
    # directory is missing does NOT — it never enters ``sources`` and therefore
    # never appends the sixth line.
    include_workbuddy = "workbuddy" in result.sources
    wrote: list[Path] = []

    if command == "inventory":
        view = build_inventory(
            result.records,
            generated_at=result.generated_at,
            warnings=warnings,
            include_workbuddy_caliber=include_workbuddy,
        )
        wrote = write_view(view, config.out_dir, "inventory", config.formats)
    elif command == "usage":
        view = build_usage(
            result.records,
            generated_at=result.generated_at,
            since=config.since,
            warnings=warnings,
            include_workbuddy_caliber=include_workbuddy,
        )
        wrote = write_view(view, config.out_dir, "usage", config.formats)
    elif command == "card":
        requested = str(args.skill_id)
        record = next(
            (item for item in result.records if item.skill_id == requested), None
        )
        if record is None:
            resolved = _resolve_skill_id(requested)
            record = next(
                (item for item in result.records if item.skill_id == resolved), None
            )
        if record is None:
            error(f"skill_id not found: {args.skill_id}")
            return EXIT_CLI
        view = build_card(
            result.records,
            record.skill_id,
            generated_at=result.generated_at,
            warnings=warnings,
            include_workbuddy_caliber=include_workbuddy,
        )
        basename = "card-" + slug_safe(record.skill_id)
        wrote = write_view(view, config.out_dir, basename, config.formats)
    elif command == "mirror":
        view = build_mirror(
            result.records,
            generated_at=result.generated_at,
            warnings=warnings,
            include_workbuddy_caliber=include_workbuddy,
        )
        wrote = write_view(view, config.out_dir, "mirror", config.formats)
    elif command == "report":
        inventory = build_inventory(
            result.records,
            generated_at=result.generated_at,
            warnings=warnings,
            include_workbuddy_caliber=include_workbuddy,
        )
        usage = build_usage(
            result.records,
            generated_at=result.generated_at,
            since=config.since,
            warnings=warnings,
            include_workbuddy_caliber=include_workbuddy,
        )
        mirror = build_mirror(
            result.records,
            generated_at=result.generated_at,
            warnings=warnings,
            include_workbuddy_caliber=include_workbuddy,
        )
        combined = {
            "title": "技能治理综合报告 (report)",
            "generated_at": result.generated_at,
            "summary": {
                "total": len(result.records),
                "sources": ", ".join(result.sources) or "(none)",
                "usage_window": config.since or "all-time",
            },
            "sections": (
                inventory["sections"] + usage["sections"] + mirror["sections"]
            ),
            "footer": inventory["footer"],
            "warnings": warnings,
        }
        wrote += write_view(inventory, config.out_dir, "inventory", config.formats)
        wrote += write_view(usage, config.out_dir, "usage", config.formats)
        wrote += write_view(mirror, config.out_dir, "mirror", config.formats)
        wrote += write_view(combined, config.out_dir, "report", config.formats)
    else:  # pragma: no cover - argparse guarantees a valid command
        raise ConfigError(f"unknown command: {command}")

    for path in wrote:
        print(str(path))
    return EXIT_OK


def _write_records_store(config: Config, result: RunResult) -> Path:
    """Persist the normalized records through the store layer (P0-4).

    The payload is deterministic (no ``generated_at``), sanitized via the single
    redaction gate and written atomically, so ``records.json`` is a stable,
    machine-consumable intermediate artifact.
    """
    payload = {
        "sources": list(result.sources),
        "warnings": list(result.warnings),
        "records": [record.to_dict() for record in result.records],
    }
    return write_json_atomic(
        config.out_dir / "records.json", sanitize_obj(payload)
    )


def _run(args: argparse.Namespace) -> int:
    """Execute one parsed invocation and return its exit code."""
    try:
        config = _build_config(args)
    except ConfigError as exc:
        error(str(exc))
        return EXIT_CLI

    reporter = Reporter()
    result = collect(config, reporter)

    if not result.sources:
        reporter.degrade(DegradeReason.NO_SOURCES, "no usable data source found")
        result.warnings = list(reporter.warnings)
        error("no usable data source (exit 3)")
        return EXIT_NO_SOURCE

    store_path = _write_records_store(config, result)
    print(str(store_path))
    return _write_command_outputs(args, config, result)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse uses SystemExit for --help/--version/errors
        code = exc.code
        return int(code) if isinstance(code, int) else EXIT_CLI

    try:
        return _run(args)
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        error("interrupted")
        return EXIT_INTERNAL
    except SkillgovError as exc:
        error(str(exc))
        return EXIT_INTERNAL
    except Exception as exc:  # noqa: BLE001 - last-resort guard
        error(f"unexpected internal error: {exc}")
        return EXIT_INTERNAL


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
