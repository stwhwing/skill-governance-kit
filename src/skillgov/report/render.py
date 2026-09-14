"""Report rendering: a neutral "view" document rendered to Markdown or JSON.

A *view* is a plain, JSON-serializable dict::

    {
      "title": str,
      "generated_at": str,
      "summary": {label: value, ...},
      "sections": [
        {"heading": str, "type": "table", "columns": [...], "rows": [[...], ...]},
        {"heading": str, "type": "list",  "items": [...]},
        {"heading": str, "type": "kv",    "items": [[k, v], ...]},
        {"heading": str, "type": "text",  "text": str},
      ],
      "footer": [str, ...],
      "warnings": [str, ...],
    }

Rendering is the *only* point where output leaves the system, and it always
routes the view through :func:`skillgov.sanitize.sanitize_obj` first — the
single redaction gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Union

from ..sanitize import sanitize_obj
from ..store.json_store import write_text_atomic

# Caliber declarations fixed into every report footer (and mirrored in README).
#
# These five lines are the v0.1 contract and MUST stay stable: a run that does
# not include the WorkBuddy ecosystem has to remain byte-identical to v0.1
# (spec E). The WorkBuddy caliber line is therefore *conditionally* appended —
# see :func:`caliber_footer`.
CALIBER_FOOTER: tuple[str, ...] = (
    "口径声明：Hermes 使用 = skill_view 标准加载（不含 read_file / terminal 直读）。",
    "口径声明：OpenClaw 使用 = 仅 trajectory 的 arguments.path 严口径计入 use_count；消息正文引用仅作旁证。",
    "口径声明：OpenClaw 会话快照内嵌技能目录（skills.entries）永不 计入使用。",
    "口径声明：全程只读采集；缺失数据源将降级并把原因记录到 warnings。",
    "口径声明：同输入重复运行，输出除 generated_at 外逐字节一致（幂等）。",
)

# WorkBuddy caliber (spec A / README §WorkBuddy). Kept in sync with the README
# wording; appended only when the run contains the WorkBuddy ecosystem.
WORKBUDDY_CALIBER_LINE = (
    "口径声明：WorkBuddy 使用 = usage-log.json 台账 recentDates 的使用天数"
    "（按使用天数计，非调用次数）；台账不跟踪 view/patch，view_count / patch_count 恒为 0；"
    "last_used_at = lastUsedDate 当日 00:00:00Z；台账键在技能树中无对应目录者记 "
    "orphan_ledger_entry 告警且不生成记录。"
)


def caliber_footer(include_workbuddy: bool = False) -> tuple[str, ...]:
    """Return the caliber footer for a run.

    Without WorkBuddy the footer is exactly the v0.1 five lines. The sixth
    (WorkBuddy) line is appended **only when the WorkBuddy ecosystem is part of
    the run** — that is, when ``<workbuddy-root>/skills`` exists and therefore
    ``"workbuddy"`` enters ``RunResult.sources``. This is a statement about the
    run's *coverage*, not about the ``--workbuddy-root`` argument: a root whose
    ``skills`` directory is missing (or no root at all) keeps the five v0.1
    lines, while a root with an existing but empty/unusable tree still counts
    and gets the sixth line.
    """
    if include_workbuddy:
        return CALIBER_FOOTER + (WORKBUDDY_CALIBER_LINE,)
    return CALIBER_FOOTER


def has_workbuddy_ecosystem(records: Iterable[Any]) -> bool:
    """Whether any record in *records* belongs to the WorkBuddy ecosystem."""
    return any(getattr(record, "ecosystem", None) == "workbuddy" for record in records)


def resolve_include_workbuddy(
    records: Iterable[Any], explicit: Union[bool, None] = None
) -> bool:
    """Decide whether the WorkBuddy caliber line applies.

    ``explicit`` (from ``RunResult.sources``) wins when provided; otherwise the
    presence of a WorkBuddy record decides. The explicit criterion is the
    authoritative one for the CLI: ``"workbuddy"`` in ``sources`` means the
    WorkBuddy *skills directory exists*, so a present-but-empty tree still
    counts, whereas a missing ``skills`` directory never enters ``sources`` and
    therefore never adds the sixth line.
    """
    if explicit is not None:
        return explicit
    return has_workbuddy_ecosystem(records)


VALID_FORMATS = ("md", "json")


def base_view(
    title: str,
    generated_at: str,
    *,
    warnings: Iterable[str] = (),
    footer: Iterable[str] = CALIBER_FOOTER,
) -> dict[str, Any]:
    """Create an empty view document with the shared footer and warnings."""
    return {
        "title": title,
        "generated_at": generated_at,
        "summary": {},
        "sections": [],
        "footer": list(footer),
        "warnings": list(warnings),
    }


def _cell(value: Any) -> str:
    """Render a single table/list cell, neutralising pipes and newlines."""
    if value is None:
        return "-"
    text = str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()
    return text if text else "-"


def to_markdown(view: dict[str, Any]) -> str:
    """Render a (already sanitized) view document to Markdown."""
    lines: list[str] = []
    lines.append(f"# {view.get('title', 'skillgov report')}")
    lines.append("")
    if view.get("generated_at"):
        lines.append(f"**generated_at**: {view['generated_at']}")
        lines.append("")

    summary = view.get("summary") or {}
    if summary:
        for key, value in summary.items():
            lines.append(f"- **{key}**: {_cell(value)}")
        lines.append("")

    for section in view.get("sections", []):
        lines.append(f"## {section.get('heading', '')}")
        lines.append("")
        section_type = section.get("type")
        if section_type == "table":
            columns = section.get("columns", [])
            rows = section.get("rows", [])
            lines.append("| " + " | ".join(_cell(col) for col in columns) + " |")
            lines.append("| " + " | ".join("---" for _ in columns) + " |")
            if rows:
                for row in rows:
                    lines.append("| " + " | ".join(_cell(cell) for cell in row) + " |")
            else:
                lines.append("| " + " | ".join("(none)" for _ in columns) + " |")
            lines.append("")
        elif section_type == "list":
            items = section.get("items", [])
            if items:
                for item in items:
                    lines.append(f"- {_cell(item)}")
            else:
                lines.append("- (none)")
            lines.append("")
        elif section_type == "kv":
            items = section.get("items", [])
            if items:
                for key, value in items:
                    lines.append(f"- **{key}**: {_cell(value)}")
            else:
                lines.append("- (none)")
            lines.append("")
        elif section_type == "text":
            lines.append(str(section.get("text", "")))
            lines.append("")

    footer = view.get("footer") or []
    if footer:
        lines.append("---")
        lines.append("")
        for item in footer:
            lines.append(f"> {item}")
        lines.append("")

    warnings = view.get("warnings") or []
    if warnings:
        lines.append("### 降级与告警（warnings）")
        lines.append("")
        for item in warnings:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def render_view(view: dict[str, Any], fmt: str) -> str:
    """Sanitize *view* and render it to *fmt* (``md`` or ``json``)."""
    safe = sanitize_obj(view)
    if fmt == "json":
        return json.dumps(safe, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    if fmt == "md":
        return to_markdown(safe)
    raise ValueError(f"unsupported format: {fmt!r}")


def write_view(
    view: dict[str, Any],
    out_dir: Union[str, Path],
    basename: str,
    formats: Iterable[str],
) -> list[Path]:
    """Write *view* to ``<out_dir>/<basename>.<fmt>`` for each requested format."""
    out = Path(str(out_dir))
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fmt in formats:
        text = render_view(view, fmt)
        written.append(write_text_atomic(out / f"{basename}.{fmt}", text))
    return written
