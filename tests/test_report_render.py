"""Tests for the four report views and md/json rendering."""

from __future__ import annotations

import json
from pathlib import Path

from skillgov.config import Config
from skillgov.logging_setup import NullReporter
from skillgov.normalize.model import SkillRecord, UsageRecord
from skillgov.report.card import build_card
from skillgov.report.inventory import build_inventory
from skillgov.report.mirror import build_mirror
from skillgov.report.render import render_view
from skillgov.report.usage import build_usage


def _collect(hermes_root: Path, openclaw_root: Path, out_dir: Path):
    from skillgov.cli.main import collect

    config = Config(hermes_root=hermes_root, openclaw_root=openclaw_root, out_dir=out_dir)
    return collect(config, NullReporter())


def test_inventory_view_renders_md_and_json(hermes_root, openclaw_root, tmp_path) -> None:
    result = _collect(hermes_root, openclaw_root, tmp_path / "out")
    view = build_inventory(result.records, generated_at=result.generated_at)

    assert view["summary"]["total"] == 5
    assert view["summary"]["hermes"] == 3
    assert view["summary"]["openclaw"] == 2

    markdown = render_view(view, "md")
    assert "# 技能全貌清单 (inventory)" in markdown
    assert "demo-alpha" in markdown

    payload = json.loads(render_view(view, "json"))
    assert payload["sections"][0]["rows"]
    assert any(row[0] == "hermes:demo-alpha" for row in payload["sections"][0]["rows"])


def test_usage_zero_and_used_split(hermes_root, openclaw_root, tmp_path) -> None:
    result = _collect(hermes_root, openclaw_root, tmp_path / "out")
    view = build_usage(result.records, generated_at=result.generated_at)
    assert view["summary"]["used"] == 3
    assert view["summary"]["zero_usage"] == 2

    windowed = build_usage(
        result.records, generated_at=result.generated_at, since="2025-01-15"
    )
    # demo-alpha (hermes) last used 2025-02-01 stays "used"; the rest fall out.
    assert windowed["summary"]["used"] == 1


def test_mirror_pairing_and_drift(hermes_root, openclaw_root, tmp_path) -> None:
    result = _collect(hermes_root, openclaw_root, tmp_path / "out")
    view = build_mirror(result.records, generated_at=result.generated_at)
    assert view["summary"]["pairs"] == 1
    assert view["summary"]["clean"] == 1
    assert view["sections"][0]["rows"][0][0] == "demo-alpha"


def test_card_known_and_unknown(hermes_root, openclaw_root, tmp_path) -> None:
    result = _collect(hermes_root, openclaw_root, tmp_path / "out")
    card = build_card(result.records, "hermes:demo-alpha", generated_at=result.generated_at)
    assert card["summary"]["found"] is True
    assert any(section["heading"] == "来源证据 (provenance)" for section in card["sections"])

    missing = build_card(result.records, "hermes:nope", generated_at=result.generated_at)
    assert missing["summary"]["found"] is False


SERVER_SAMPLE = "111." + "229." + "70." + "191"


def test_render_sanitizes_output() -> None:
    private = f"server {SERVER_SAMPLE} leaked"
    record = SkillRecord(
        skill_id="hermes:demo-alpha",
        name="demo-alpha",
        ecosystem="hermes",
        path="skills/demo-alpha",
        presence="active",
        category="demo-alpha",
        description=private,
        usage=UsageRecord(use_count=1),
    )
    view = build_inventory([record], generated_at="2025-01-01T00:00:00Z")
    markdown = render_view(view, "md")
    payload = json.loads(render_view(view, "json"))

    assert SERVER_SAMPLE not in markdown
    assert "<SERVER>" in markdown
    assert SERVER_SAMPLE not in json.dumps(payload)


def test_render_rejects_unknown_format() -> None:
    import pytest

    with pytest.raises(ValueError):
        render_view({"title": "x"}, "xml")
