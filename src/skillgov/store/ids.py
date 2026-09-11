"""Deterministic skill identifier derivation.

``skill_id`` is ``f"{ecosystem}:{rel_path_slug}"`` where the slug is derived from
the skill directory relative to its skills tree (for example ``demo-alpha`` or
``archive-demo-old``).

Defence-in-depth rule (P0-6): the raw path is passed through the redaction
gate :func:`skillgov.sanitize.sanitize` **before** slugging. A directory whose
name embeds a sensitive literal (for example an IPv4 address) therefore yields
a redacted, stable identifier (``<SERVER>`` -> ``server``) instead of a
dash-encoded leak. The same gate backs :func:`slug_safe`, which produces
file-system-safe basenames for output artifacts such as archive cards.
"""

from __future__ import annotations

import re

from ..sanitize import sanitize

_SLUG_RE = re.compile(r"[^A-Za-z0-9_-]+")
_COLLAPSE_RE = re.compile(r"-{2,}")


def rel_path_slug(rel_path: str) -> str:
    """Slugify a relative skill directory into an identifier-safe token.

    The input is sanitized *before* slugging so sensitive directory names can
    never resurface in dash-encoded form.
    """
    text = sanitize(str(rel_path)).replace("\\", "/").strip()
    if text.endswith("/SKILL.md"):
        text = text[: -len("/SKILL.md")]
    text = text.strip("/")
    text = _SLUG_RE.sub("-", text)
    text = text.strip("-").lower()
    return text or "root"


def make_skill_id(ecosystem: str, rel_path: str) -> str:
    """Return the stable ``<ecosystem>:<slug>`` identifier for a skill."""
    return f"{ecosystem}:{rel_path_slug(rel_path)}"


def slug_safe(text: str) -> str:
    """Return a deterministic, file-system-safe slug for *text*.

    Sanitizes first, then replaces every character outside
    ``[A-Za-z0-9._-]`` with ``-`` (redaction placeholders such as ``<SERVER>``
    are not legal on all file systems), collapses runs of dashes and lowercases
    the result. Same input -> same output, which keeps artifact names
    reproducible.
    """
    slug = _SLUG_RE.sub("-", sanitize(str(text)))
    slug = _COLLAPSE_RE.sub("-", slug).strip("-").lower()
    return slug or "redacted"
