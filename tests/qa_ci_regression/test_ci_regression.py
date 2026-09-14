"""QA-CI independent regression probes (authored by Edward / QA).

These probes are written from scratch — own payloads, own helper walkers — so
they can *falsify* the determinism fix if it is wrong. They are strictly
read-only with respect to the repository: they never regenerate or modify
``examples/out/**``.

Covered:
* the ENV_DEPENDENT_FIELDS contract is the single source of truth and agrees
  with the README "two environment-dependent fields" wording;
* ``normalize_env_dependent`` purity + idempotence;
* all three payload shapes (records mapping key, table ``columns``/``rows``,
  ``kv`` ``[k, v]`` pairs) including a nested list-of-lists variant;
* ``generated_at`` DROP (default) vs fixed-value replacement;
* ``find_env_dependent`` detection;
* the committed ``examples/out/**`` snapshots are environment-free and each
  view ``*.md`` is the render of its normalised ``*.json``.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from skillgov.determinism import (
    CREATED_AT_FIELD,
    DROP,
    ENV_DEPENDENT_FIELDS,
    GENERATED_AT_FIELD,
    find_env_dependent,
    normalize_env_dependent,
)
from skillgov.report.render import render_view

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "examples" / "out"
VIEWS = ("inventory", "usage", "mirror", "report")

# A deliberately distinctive, non-null environment stamp.
STAMP = "2024-12-31T23:59:59Z"


def _walk_keys(node, key, hits):
    """Collect every value stored under *key* anywhere in *node*."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                hits.append(v)
            else:
                _walk_keys(v, key, hits)
    elif isinstance(node, list):
        for item in node:
            _walk_keys(item, key, hits)
    return hits


# --------------------------------------------------------------- contract ----
def test_env_dependent_fields_is_exactly_the_two_named_constants() -> None:
    assert ENV_DEPENDENT_FIELDS == (CREATED_AT_FIELD, GENERATED_AT_FIELD)
    assert ENV_DEPENDENT_FIELDS == ("created_at", "generated_at")


def test_readme_agrees_with_the_two_field_contract() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Determinism" in readme
    for field in ENV_DEPENDENT_FIELDS:
        assert f"`{field}`" in readme, field
    # "exactly two environment-dependent fields" (EN) OR the Chinese equivalent
    assert (
        "two environment-dependent fields" in readme.lower()
        or "仅有的两个环境相关字段" in readme
    )


# ---------------------------------------------------------------- purity -----
def test_normalize_records_payload_is_pure() -> None:
    payload = {"records": [{"skill_id": "x", "created_at": STAMP}], "generated_at": STAMP}
    snapshot = copy.deepcopy(payload)
    _ = normalize_env_dependent(payload)
    assert payload == snapshot


def test_normalize_table_and_kv_payload_is_pure() -> None:
    payload = {
        "generated_at": STAMP,
        "sections": [
            {"columns": ["skill_id", "created_at"], "rows": [["a", STAMP]]},
            {"type": "kv", "items": [["created_at", STAMP], ["name", "a"]]},
        ],
    }
    snapshot = copy.deepcopy(payload)
    _ = normalize_env_dependent(payload)
    assert payload == snapshot


# ---------------------------------------------------------------- shapes -----
def test_records_mapping_key_is_nulled() -> None:
    result = normalize_env_dependent({"records": [{"created_at": STAMP}]})
    assert result["records"][0]["created_at"] is None


def test_table_column_is_located_via_columns_header() -> None:
    view = {
        "sections": [
            {
                "columns": ["skill_id", "created_at", "version"],
                "rows": [["a", STAMP, "1.0"], ["b", None, "2.0"]],
            }
        ]
    }
    rows = normalize_env_dependent(view)["sections"][0]["rows"]
    assert [row[1] for row in rows] == [None, None]
    assert rows[0][0] == "a" and rows[0][2] == "1.0"


def test_table_without_created_at_column_is_untouched() -> None:
    view = {"sections": [{"columns": ["skill_id"], "rows": [["a"]]}]}
    result = normalize_env_dependent(view)
    assert result["sections"][0]["rows"] == [["a"]]


def test_kv_pair_is_nulled() -> None:
    view = {"sections": [{"type": "kv", "items": [["name", "a"], ["created_at", STAMP]]}]}
    items = dict(normalize_env_dependent(view)["sections"][0]["items"])
    assert items["created_at"] is None and items["name"] == "a"


def test_deeply_nested_created_at_is_nulled() -> None:
    payload = {
        "outer": {"inner": [{"created_at": STAMP}, {"created_at": STAMP}]},
    }
    result = normalize_env_dependent(payload)
    assert _walk_keys(result, "created_at", []) == [None, None]


# ----------------------------------------------------------- generated_at ----
def test_generated_at_is_dropped_by_default() -> None:
    result = normalize_env_dependent({"generated_at": STAMP, "title": "t"})
    assert GENERATED_AT_FIELD not in result
    assert result["title"] == "t"


def test_generated_at_replaced_with_fixed_value_when_requested() -> None:
    result = normalize_env_dependent(
        {"generated_at": STAMP, "title": "t"}, generated_at="<GENERATED_AT>"
    )
    assert result["generated_at"] == "<GENERATED_AT>"


def test_generated_at_drop_reaches_nested_nodes() -> None:
    payload = {"a": {"generated_at": STAMP}, "b": [{"generated_at": STAMP}]}
    result = normalize_env_dependent(payload)
    assert GENERATED_AT_FIELD not in result["a"]
    assert GENERATED_AT_FIELD not in result["b"][0]


def test_drop_sentinel_is_the_public_default_policy() -> None:
    assert DROP is not None
    assert normalize_env_dependent({"generated_at": "x"}) == {}


# ------------------------------------------------------------- idempotence ---
def test_normalize_is_idempotent_across_all_shapes() -> None:
    payload = {
        "generated_at": STAMP,
        "records": [{"created_at": STAMP}],
        "sections": [
            {"columns": ["created_at"], "rows": [[STAMP]]},
            {"type": "kv", "items": [["created_at", STAMP]]},
        ],
    }
    once = normalize_env_dependent(payload)
    assert normalize_env_dependent(once) == once


# --------------------------------------------------------- find_env_depend ---
def test_find_env_dependent_empty_for_clean_payload() -> None:
    clean = {
        "records": [{"created_at": None}],
        "sections": [{"columns": ["created_at"], "rows": [[None]]}],
    }
    assert find_env_dependent(clean) == []


def test_find_env_dependent_flags_every_shape() -> None:
    assert find_env_dependent({"records": [{"created_at": STAMP}]})
    assert find_env_dependent({"sections": [{"columns": ["created_at"], "rows": [[STAMP]]}]})
    assert find_env_dependent({"sections": [{"type": "kv", "items": [["created_at", STAMP]]}]})
    assert find_env_dependent({"generated_at": None})  # presence is enough


# ------------------------------------------------------- examples purity -----
def test_examples_json_are_environment_free() -> None:
    files = sorted(EXAMPLES.glob("*.json"))
    assert files, "examples/out must ship JSON snapshots"
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        leaks = find_env_dependent(payload)
        assert leaks == [], f"{path.name} leaks {leaks}"


def test_examples_have_no_generated_at_and_null_created_at() -> None:
    for path in sorted(EXAMPLES.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert _walk_keys(payload, "generated_at", []) == [], path.name
        for value in _walk_keys(payload, "created_at", []):
            assert value is None, (path.name, value)


def test_examples_view_markdown_matches_normalised_json() -> None:
    for view in VIEWS:
        payload = json.loads((EXAMPLES / f"{view}.json").read_text(encoding="utf-8"))
        assert (EXAMPLES / f"{view}.md").read_text(encoding="utf-8") == render_view(
            payload, "md"
        ), view


def test_examples_records_created_at_is_null() -> None:
    records = json.loads((EXAMPLES / "records.json").read_text(encoding="utf-8"))["records"]
    assert records, "expected records in examples/out/records.json"
    assert all(row["created_at"] is None for row in records)
