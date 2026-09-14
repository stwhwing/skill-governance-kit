"""Unit tests for :mod:`skillgov.determinism` (the determinism contract).

The module is the single, pure implementation shared by the test-suite and
``scripts/regen_examples.py``; these tests pin its behaviour for every shape it
must normalise (records payloads, table sections and ``kv`` sections).
"""

from __future__ import annotations

import copy

from skillgov.determinism import (
    CREATED_AT_FIELD,
    DROP,
    ENV_DEPENDENT_FIELDS,
    GENERATED_AT_FIELD,
    normalize_env_dependent,
    find_env_dependent,
)

SAMPLE_CTIME = "2026-09-11T02:09:51Z"
SAMPLE_GENERATED = "2026-09-14T01:48:16Z"


def test_contract_names_exactly_two_environment_dependent_fields() -> None:
    assert ENV_DEPENDENT_FIELDS == (CREATED_AT_FIELD, GENERATED_AT_FIELD)
    assert ENV_DEPENDENT_FIELDS == ("created_at", "generated_at")


def test_records_payload_created_at_is_nulled() -> None:
    payload = {
        "records": [
            {"skill_id": "a", "created_at": SAMPLE_CTIME},
            {"skill_id": "b", "created_at": None},
        ]
    }
    result = normalize_env_dependent(payload)
    assert [row["created_at"] for row in result["records"]] == [None, None]
    assert [row["skill_id"] for row in result["records"]] == ["a", "b"]


def test_generated_at_is_dropped_by_default() -> None:
    payload = {"generated_at": SAMPLE_GENERATED, "title": "t"}
    result = normalize_env_dependent(payload)
    assert GENERATED_AT_FIELD not in result
    assert result["title"] == "t"


def test_generated_at_can_be_replaced_with_a_fixed_placeholder() -> None:
    payload = {"generated_at": SAMPLE_GENERATED, "title": "t"}
    result = normalize_env_dependent(payload, generated_at="<GENERATED_AT>")
    assert result["generated_at"] == "<GENERATED_AT>"
    assert result["title"] == "t"


def test_table_created_at_column_is_located_via_columns() -> None:
    view = {
        "generated_at": SAMPLE_GENERATED,
        "sections": [
            {
                "columns": ["skill_id", "created_at", "version"],
                "rows": [
                    ["a", SAMPLE_CTIME, "1.0"],
                    ["b", None, "2.0"],
                ],
                "type": "table",
            }
        ],
    }
    result = normalize_env_dependent(view)
    rows = result["sections"][0]["rows"]
    assert [row[1] for row in rows] == [None, None]
    # non-environmental cells are untouched
    assert rows[0][0] == "a" and rows[0][2] == "1.0"
    # the column header itself stays
    assert result["sections"][0]["columns"][1] == "created_at"


def test_kv_created_at_pair_is_nulled() -> None:
    view = {
        "sections": [
            {
                "type": "kv",
                "items": [["name", "a"], ["created_at", SAMPLE_CTIME]],
            }
        ]
    }
    result = normalize_env_dependent(view)
    items = dict(result["sections"][0]["items"])
    assert items["created_at"] is None
    assert items["name"] == "a"


def test_normalize_is_pure_and_does_not_mutate_input() -> None:
    payload = {
        "generated_at": SAMPLE_GENERATED,
        "records": [{"created_at": SAMPLE_CTIME}],
        "sections": [{"columns": ["created_at"], "rows": [[SAMPLE_CTIME]]}],
    }
    snapshot = copy.deepcopy(payload)
    _ = normalize_env_dependent(payload)
    assert payload == snapshot


def test_normalize_is_idempotent() -> None:
    payload = {
        "generated_at": SAMPLE_GENERATED,
        "records": [{"created_at": SAMPLE_CTIME}],
        "sections": [
            {"columns": ["created_at"], "rows": [[SAMPLE_CTIME]]},
            {"type": "kv", "items": [["created_at", SAMPLE_CTIME]]},
        ],
    }
    once = normalize_env_dependent(payload)
    twice = normalize_env_dependent(once)
    assert once == twice


def test_drop_sentinel_is_the_default_policy() -> None:
    assert DROP is not None
    assert normalize_env_dependent({"generated_at": "x"}) == {}


def test_find_env_dependent_clean_payload_has_no_hits() -> None:
    normalized = {
        "records": [{"created_at": None}],
        "sections": [{"columns": ["created_at"], "rows": [[None]]}],
    }
    assert find_env_dependent(normalized) == []


def test_find_env_dependent_reports_created_at_leaks() -> None:
    assert len(find_env_dependent({"records": [{"created_at": SAMPLE_CTIME}]})) == 1
    table = {"sections": [{"columns": ["created_at"], "rows": [[SAMPLE_CTIME]]}]}
    assert len(find_env_dependent(table)) == 1
    kv = {"sections": [{"type": "kv", "items": [["created_at", SAMPLE_CTIME]]}]}
    assert len(find_env_dependent(kv)) == 1


def test_find_env_dependent_reports_any_generated_at() -> None:
    assert find_env_dependent({"generated_at": SAMPLE_GENERATED}) != []
    assert find_env_dependent({"generated_at": None}) != []
