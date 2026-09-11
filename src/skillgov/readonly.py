"""Read-only guardrail: read-only opens, a write blocker and a tree snapshot.

The collector must never mutate an inspected tree. This module provides:

* :func:`open_readonly` / :func:`read_text` — text reads always in ``"r"`` mode.
* :func:`sqlite_ro` — SQLite connections always via a ``mode=ro`` URI.
* :func:`snapshot_tree` — a lightweight, deterministic fingerprint
  (file count + total bytes + digest of ``<relpath, size, mtime_ns>``).
* :func:`assert_no_writes` — raise :class:`~skillgov.errors.ReadOnlyViolation`
  when two snapshots differ, so callers can assert "zero writes".
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Optional, Union

from .errors import ReadOnlyViolation


def open_readonly(path: Union[str, Path]) -> IO[str]:
    """Open *path* for text reading only (UTF-8, replacement on decode errors)."""
    return open(str(path), "r", encoding="utf-8", errors="replace")


def read_text(path: Union[str, Path], limit: Optional[int] = None) -> str:
    """Read a text file read-only; return ``""`` when it cannot be read."""
    try:
        with open_readonly(path) as handle:
            return handle.read() if limit is None else handle.read(limit)
    except OSError:
        return ""


def sqlite_ro(db_path: Union[str, Path]) -> sqlite3.Connection:
    """Open *db_path* as a strictly read-only SQLite connection.

    Uses the SQLite ``mode=ro`` URI so that even accidental writes fail. Raises
    :class:`FileNotFoundError` when the database file does not exist.
    """
    path = Path(str(db_path))
    if not path.is_file():
        raise FileNotFoundError(f"sqlite database not found: {path.name}")
    uri = path.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


@dataclass(frozen=True)
class TreeSnapshot:
    """Immutable fingerprint of a directory tree."""

    root: str
    file_count: int
    total_bytes: int
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "digest": self.digest,
        }


def snapshot_tree(root: Union[str, Path]) -> TreeSnapshot:
    """Return a deterministic :class:`TreeSnapshot` for *root*.

    Directories are walked with sorted names and each regular file contributes a
    ``<relpath, size, mtime_ns>`` line, so identical trees always produce the
    same digest. A missing root yields an empty (zero-file) snapshot.
    """
    root_path = Path(str(root))
    lines: list[str] = []
    file_count = 0
    total_bytes = 0

    if root_path.exists():
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames.sort()
            filenames.sort()
            for filename in filenames:
                file_path = Path(dirpath) / filename
                try:
                    stat = file_path.lstat()
                except OSError:
                    continue
                try:
                    rel = file_path.relative_to(root_path).as_posix()
                except ValueError:
                    rel = filename
                lines.append(f"{rel}\t{stat.st_size}\t{stat.st_mtime_ns}")
                file_count += 1
                total_bytes += stat.st_size

    digest = hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()
    return TreeSnapshot(
        root=str(root_path),
        file_count=file_count,
        total_bytes=total_bytes,
        digest=digest,
    )


def snapshots_equal(before: TreeSnapshot, after: TreeSnapshot) -> bool:
    """Whether two snapshots describe the same tree state."""
    return (
        before.file_count == after.file_count
        and before.total_bytes == after.total_bytes
        and before.digest == after.digest
    )


def assert_no_writes(before: TreeSnapshot, after: TreeSnapshot) -> None:
    """Raise :class:`ReadOnlyViolation` if *after* differs from *before*."""
    if not snapshots_equal(before, after):
        raise ReadOnlyViolation(
            "read-only guard: tree changed during run "
            f"(files {before.file_count}->{after.file_count}, "
            f"bytes {before.total_bytes}->{after.total_bytes})"
        )
