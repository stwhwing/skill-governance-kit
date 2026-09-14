"""Atomic, idempotent JSON/text persistence helpers.

Reads are plain read-only opens. Writes are atomic (temp file + ``os.replace``)
and target only the output directory — never an inspected tree. Serialization is
deterministic (``sort_keys=True``, UTF-8, 2-space indent) so two runs over the
same input differ, at most, by the two environment-dependent fields ``generated_at`` and ``created_at`` (the latter is null on platforms without file-birth-time support).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Union

PathLike = Union[str, Path]


def dumps_stable(obj: Any) -> str:
    """Deterministic JSON text: sorted keys, UTF-8, two-space indent."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2)


def write_text_atomic(path: PathLike, text: str) -> Path:
    """Write *text* to *path* atomically and return the final path."""
    target = Path(str(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, temp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=".tmp-", suffix=target.suffix
    )
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except OSError:
                pass
    return target


def write_json_atomic(path: PathLike, obj: Any) -> Path:
    """Serialize *obj* deterministically and write it atomically."""
    return write_text_atomic(path, dumps_stable(obj) + "\n")
