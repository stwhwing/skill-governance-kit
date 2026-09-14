"""The determinism contract for ``skillgov`` artifacts.

``skillgov`` advertises byte-stable output: two runs over the same input must
produce identical JSON. Exactly **two** fields are inherently
environment-dependent and are therefore excluded from that promise:

* ``generated_at`` — the wall-clock time of the run (``utc_now_iso``). It
  changes on every invocation and is meaningless for a committed snapshot.
* ``created_at`` — the best-effort *file creation time* of a ``SKILL.md``. It
  is read by :func:`skillgov.adapters.fs_scan._birth_time`, which uses
  ``st_birthtime`` where the OS exposes it and falls back to ``st_ctime`` on
  Windows. On POSIX hosts without ``st_birthtime`` it is ``None``, and on any
  host the value changes on each checkout — it can never be reproduced across
  machines.

Every *other* field must be byte-stable. :func:`normalize_env_dependent`
turns a payload into its environment-free form by setting every ``created_at``
to ``None`` and (by default) dropping ``generated_at`` entirely. The committed
snapshots under ``examples/out/**`` are stored in exactly this normalised form;
the test-suite guards that they stay that way (see
``tests/test_v02_fixes.py`` and ``tests/test_determinism.py``).

This module is intentionally dependency-free and side-effect-free: both helpers
are pure functions over plain JSON-compatible structures.
"""

from __future__ import annotations

import copy
from typing import Any

# The complete, closed set of environment-dependent field names. If a field is
# ever added here the README "Determinism" section must be updated with it.
CREATED_AT_FIELD = "created_at"
GENERATED_AT_FIELD = "generated_at"
ENV_DEPENDENT_FIELDS: tuple[str, ...] = (CREATED_AT_FIELD, GENERATED_AT_FIELD)

# ``created_at`` is normalised to this value everywhere it appears.
CREATED_AT_NORMALIZED: None = None


class _Drop:
    """Sentinel type meaning "remove the ``generated_at`` key entirely"."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "DROP"


# Sentinel value: the default policy passed as ``generated_at``.
DROP = _Drop()


def normalize_env_dependent(payload: Any, *, generated_at: Any = DROP) -> Any:
    """Return a deep, environment-free copy of *payload*.

    The normalisation implements the determinism contract above:

    * every ``created_at`` — whether it is a mapping key, a cell of a table
      section (located through the sibling ``columns`` list) or the value of a
      ``[key, value]`` pair in a ``kv`` section — is replaced with ``None``;
    * ``generated_at`` is **removed** by default. Pass a concrete value (for
      example the placeholder ``"<GENERATED_AT>"``) to replace it instead of
      dropping it, when a caller needs to keep the field but freeze its value.

    The function is pure: *payload* is never mutated (a deep copy is returned)
    and the result is idempotent — ``normalize_env_dependent`` applied twice
    yields the same value as applied once.
    """
    return _normalize(copy.deepcopy(payload), generated_at)


def find_env_dependent(payload: Any) -> list[tuple[str, Any]]:
    """Return every un-normalised environment-dependent value in *payload*.

    An occurrence is reported when:

    * a ``created_at`` value is not ``None`` (a real OS timestamp leaked in), or
    * a ``generated_at`` key is present at all (with any value).

    An empty result therefore means *payload* is fully normalised — which is the
    invariant the committed ``examples/out/**`` snapshots must satisfy.
    """
    found: list[tuple[str, Any]] = []
    _collect(payload, "$", found)
    return found


def _normalize(node: Any, generated_at: Any) -> Any:
    """Recursively normalise *node* in place (it is already a private copy)."""
    if isinstance(node, dict):
        _normalize_table_rows(node)
        _normalize_kv_items(node)
        for key in list(node.keys()):
            value = node[key]
            if key == CREATED_AT_FIELD:
                node[key] = CREATED_AT_NORMALIZED
            elif key == GENERATED_AT_FIELD:
                if generated_at is DROP:
                    del node[key]
                else:
                    node[key] = generated_at
            else:
                node[key] = _normalize(value, generated_at)
        return node
    if isinstance(node, list):
        return [_normalize(item, generated_at) for item in node]
    return node


def _normalize_table_rows(node: dict[str, Any]) -> None:
    """Null out the ``created_at`` column of a ``columns``/``rows`` section."""
    columns = node.get("columns")
    rows = node.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return
    indexes = [
        index
        for index, name in enumerate(columns)
        if name == CREATED_AT_FIELD
    ]
    if not indexes:
        return
    for row in rows:
        if isinstance(row, list):
            for index in indexes:
                if index < len(row):
                    row[index] = CREATED_AT_NORMALIZED


def _normalize_kv_items(node: dict[str, Any]) -> None:
    """Null out the ``created_at`` value of a ``kv`` section's items."""
    items = node.get("items")
    if not isinstance(items, list):
        return
    for pair in items:
        if (
            isinstance(pair, list)
            and len(pair) == 2
            and pair[0] == CREATED_AT_FIELD
        ):
            pair[1] = CREATED_AT_NORMALIZED


def _collect(node: Any, path: str, found: list[tuple[str, Any]]) -> None:
    """Append every un-normalised env-dependent value under *node* to *found*."""
    if isinstance(node, dict):
        columns = node.get("columns")
        rows = node.get("rows")
        if isinstance(columns, list) and isinstance(rows, list):
            created_indexes = [
                index
                for index, name in enumerate(columns)
                if name == CREATED_AT_FIELD
            ]
            for row_index, row in enumerate(rows):
                if not isinstance(row, list):
                    continue
                for column_index in created_indexes:
                    if column_index < len(row) and row[column_index] is not None:
                        location = f"{path}.rows[{row_index}][{column_index}]"
                        found.append((location, row[column_index]))
        for key, value in node.items():
            child = f"{path}.{key}"
            if key == CREATED_AT_FIELD:
                if value is not None:
                    found.append((child, value))
            elif key == GENERATED_AT_FIELD:
                found.append((child, value))
            else:
                _collect(value, child, found)
        return
    if isinstance(node, list):
        for index, item in enumerate(node):
            if (
                isinstance(item, list)
                and len(item) == 2
                and item[0] == CREATED_AT_FIELD
                and item[1] is not None
            ):
                found.append((f"{path}[{index}]", item[1]))
            else:
                _collect(item, f"{path}[{index}]", found)
