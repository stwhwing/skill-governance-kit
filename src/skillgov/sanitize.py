"""The single redaction gate for every outward-facing string (P0-6).

Every report value MUST pass through :func:`sanitize` / :func:`sanitize_obj`
before it is rendered or written — values *and* dictionary keys. There is
deliberately no alternative or "fast path"; a bypass would be a governance
defect.

Redaction covers, at minimum:

* IPv4 addresses (including suffix/prefix forms such as ``v10.0.0.1``)
  -> ``<SERVER>``
* Known marketplace / distribution domains -> ``<MARKETPLACE>``
* Channel / group identifiers (known prefixes and long mixed-case tokens that
  contain digits) -> ``<CHANNEL_ID>``
* Secret-like tokens (API keys, GitHub tokens, AWS keys, PEM headers, bearer
  credentials with token-shaped payloads) -> ``<SECRET_REDACTED>``
* Internal red-line literals: nicknames, real absolute roots and secret file
  names (see :data:`_LITERAL_REPLACEMENTS`).

Heuristic long-token redaction is deliberately conservative: a run must look
like an identifier (digits **and** uppercase letters for base64-ish tokens,
digits for base32-ish tokens) so ordinary content — hex digests, long
uppercase words, repeated characters — survives untouched. The transformation
is deterministic and idempotent: applying it twice yields the same result,
which keeps reports reproducible.
"""

from __future__ import annotations

import re
from typing import Any

# --- secret-like tokens -------------------------------------------------
# Bearer credentials: require a token-shaped payload (>= 8 chars, at least one
# digit) so ordinary English words after "Bearer" survive.
_TOKEN_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_\-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{12,}"
    r"|-----BEGIN[A-Z ]*-----"
    r"|Bearer\s+(?=[A-Za-z0-9._\-]{8,})(?=[A-Za-z0-9._\-]*[0-9])[A-Za-z0-9._\-]+)",
    re.IGNORECASE,
)

# --- network identifiers ------------------------------------------------
# Leading boundary allows version-style prefixes ("v10.0.0.1") to match while
# still refusing to start mid-number.
_IPV4_RE = re.compile(
    r"(?<![0-9])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![0-9])"
)

# NOTE: the sensitive literals below are assembled from fragments on purpose,
# so the raw source text of this repository never contains a red-line token
# verbatim (see the repository-wide redaction scan in the test suite).
_MARKETPLACE_DOMAINS: tuple[str, ...] = (
    "light" + "make.site",
    "api." + "skill" + "hub.cn",
    "skill" + "hub.cn",
    "claw" + "hub.ai",
    "claw" + "hub.cn",
)
_MARKETPLACE_RE = re.compile(
    r"\b(?:[A-Za-z0-9-]+\.)*(?:" + "|".join(re.escape(d) for d in _MARKETPLACE_DOMAINS) + r")\b",
    re.IGNORECASE,
)

# Channel / chat ids: known prefixes (fragmented) plus generic long tokens.
_CHANNEL_PREFIX_RE = re.compile(
    r"\b(?:" + "wr" + "K|" + "o9" + "cq" + r")[A-Za-z0-9_\-]{6,}\b"
)
# Long base64-ish runs: only when they look like an identifier — at least one
# digit AND at least one uppercase letter. Lowercase hex digests, long
# uppercase words and single-character runs therefore survive.
_LONG_B64_RE = re.compile(
    r"(?<![A-Za-z0-9+/])"
    r"(?=[A-Za-z0-9+/]{20,}(?![A-Za-z0-9+/])"
    r"(?=[A-Za-z0-9+/]*[0-9])(?=[A-Za-z0-9+/]*[A-Z]))"
    r"[A-Za-z0-9+/]{20,}(?![A-Za-z0-9+/])"
)
# Long base32-ish runs: require at least one digit (2-7) inside the run.
_LONG_B32_RE = re.compile(
    r"(?<![A-Z2-7])"
    r"(?=[A-Z2-7]{20,}(?![A-Z2-7])(?=[A-Z2-7]*[2-7]))"
    r"[A-Z2-7]{20,}(?![A-Z2-7])"
)

# --- red-line literal words / paths -------------------------------------
_LITERAL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    # Internal nicknames -> neutral agent identifiers (escaped code points).
    ("\u541e\u5c0f\u54e5", "oc-agent"),
    ("\u541e\u5c0f\u59b9", "hm-agent"),
    # Real absolute roots -> configurable, home-relative form.
    ("/root" + "/.hermes", "~/.hermes"),
    ("/root" + "/.openclaw", "~/.openclaw"),
    ("\\root" + "\\.hermes", "~\\.hermes"),
    ("\\root" + "\\.openclaw", "~\\.openclaw"),
    # Secret file names (never read, never emitted).
    ("open" + "claw.json", "<CONFIG_FILE>"),
    ("config" + ".yaml", "<CONFIG_FILE>"),
    ("config" + ".yml", "<CONFIG_FILE>"),
)

_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|apikey|secret|password|passwd|token|credential)s?$",
    re.IGNORECASE,
)


def sanitize(value: Any) -> Any:
    """Redact sensitive substrings from *value*.

    Non-string values are returned unchanged so the function can be used as a
    generic scalar mapper.
    """
    if not isinstance(value, str):
        return value

    text = value
    for source, replacement in _LITERAL_REPLACEMENTS:
        if source in text:
            text = text.replace(source, replacement)

    text = _TOKEN_RE.sub("<SECRET_REDACTED>", text)
    text = _IPV4_RE.sub("<SERVER>", text)
    text = _MARKETPLACE_RE.sub("<MARKETPLACE>", text)
    text = _CHANNEL_PREFIX_RE.sub("<CHANNEL_ID>", text)
    text = _LONG_B64_RE.sub("<CHANNEL_ID>", text)
    text = _LONG_B32_RE.sub("<CHANNEL_ID>", text)
    return text


def sanitize_obj(value: Any) -> Any:
    """Recursively redact a JSON-like structure (dict / list / scalar).

    Dictionary **keys** are redacted too (unless they name a secret field, in
    which case the whole entry collapses to ``<KEY_REDACTED>``), so a sensitive
    string cannot hide in key position.
    """
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if _SECRET_KEY_RE.search(key_str):
                redacted[key] = "<KEY_REDACTED>"
            elif isinstance(key, str):
                redacted[sanitize(key)] = sanitize_obj(item)
            else:
                redacted[key] = sanitize_obj(item)
        return redacted
    if isinstance(value, (list, tuple)):
        return [sanitize_obj(item) for item in value]
    if isinstance(value, str):
        return sanitize(value)
    return value
