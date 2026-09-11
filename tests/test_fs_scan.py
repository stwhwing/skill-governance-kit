"""Unit tests for the filesystem scan adapter."""

from __future__ import annotations

from pathlib import Path

from skillgov.adapters.fs_scan import (
    parse_frontmatter,
    scan_skills,
    scanned_to_record,
)


def test_parse_frontmatter_basic() -> None:
    text = "---\nname: demo-alpha\ndescription: hello world\nversion: 1.0.0\n---\n\n# body\n"
    frontmatter = parse_frontmatter(text)
    assert frontmatter["name"] == "demo-alpha"
    assert frontmatter["description"] == "hello world"
    assert frontmatter["version"] == "1.0.0"


def test_parse_frontmatter_absent_returns_empty() -> None:
    assert parse_frontmatter("# no frontmatter here\n") == {}


def test_scan_skills_finds_active_and_archived(hermes_root: Path) -> None:
    scanned = scan_skills(hermes_root / "skills", archive_markers=(".archive",))
    by_rel = {item.rel_dir: item for item in scanned}
    assert set(by_rel) == {"demo-alpha", "demo-beta", ".archive/demo-old"}
    assert by_rel["demo-alpha"].presence == "active"
    assert by_rel["demo-beta"].presence == "active"
    assert by_rel[".archive/demo-old"].presence == "archived"
    assert by_rel["demo-alpha"].category == "demo-alpha"
    assert by_rel[".archive/demo-old"].category == ".archive"


def test_scan_skills_deterministic_order(hermes_root: Path) -> None:
    first = [item.rel_dir for item in scan_skills(hermes_root / "skills")]
    second = [item.rel_dir for item in scan_skills(hermes_root / "skills")]
    assert first == second == sorted(first)


def test_scan_skills_missing_dir_is_empty(tmp_path: Path) -> None:
    assert scan_skills(tmp_path / "does-not-exist") == []


def test_description_truncation() -> None:
    from skillgov.adapters.fs_scan import ScannedSkill

    long_text = "x" * 500
    item = ScannedSkill(
        rel_dir="demo-long",
        name="demo-long",
        category="demo-long",
        presence="active",
        description=long_text,
        version=None,
        generated_from=None,
        created_at=None,
    )
    record = scanned_to_record("hermes", "skills", item, description_limit=200)
    assert record.description is not None
    assert len(record.description) == 200
    assert record.skill_id == "hermes:demo-long"
    assert record.path == "skills/demo-long"
