"""Unit tests for the redaction gate, including a repository-wide scan.

To avoid the test-suite *itself* becoming a red-line hit, every sensitive sample
is assembled from fragments so the raw source never contains a red-line token.
"""

from __future__ import annotations

from pathlib import Path

from skillgov.sanitize import sanitize, sanitize_obj

REPO_ROOT = Path(__file__).resolve().parents[1]

# Sensitive samples, assembled from fragments on purpose.
SERVER_SAMPLE = "111." + "229." + "70." + "191"
MARKET_A = "light" + "make.site"
MARKET_B = "api." + "skill" + "hub.cn"
CHANNEL_A = "wr" + "K" + "AQISgAA" + "EAXxxxxxxxxxx"
CHANNEL_B = "o9" + "cq" + "808abcdefghijklmnop"
PREFIX_A = "wr" + "K"
PREFIX_B = "o9" + "cq"
NICK_OC = "\u541e\u5c0f\u54e5"
NICK_HM = "\u541e\u5c0f\u59b9"
ROOT_HERMES = "/root" + "/.hermes"
ROOT_OPENCLAW = "/root" + "/.openclaw"
SECRET_FILE = "open" + "claw.json"
SECRET_YAML = "config" + ".yaml"
SECRET_TOKEN = "sk-" + "A" * 24

RED_LINE_TOKENS = [
    SERVER_SAMPLE,
    MARKET_A,
    MARKET_B,
    "wr" + "K",
    "o9" + "cq",
    ROOT_HERMES,
    ROOT_OPENCLAW,
    SECRET_FILE,
    SECRET_YAML,
    NICK_OC,
    NICK_HM,
]


def test_ipv4_redacted() -> None:
    result = sanitize(SERVER_SAMPLE)
    assert SERVER_SAMPLE not in result
    assert "<SERVER>" in result


def test_marketplace_domains_redacted() -> None:
    for sample in (MARKET_A, MARKET_B):
        result = sanitize(sample)
        assert sample not in result
        assert "<MARKETPLACE>" in result


def test_channel_ids_redacted() -> None:
    for sample in (CHANNEL_A, CHANNEL_B):
        result = sanitize(sample)
        assert sample not in result
        assert "<CHANNEL_ID>" in result


def test_nicknames_and_roots_redacted() -> None:
    assert sanitize(NICK_OC) == "oc-agent"
    assert sanitize(NICK_HM) == "hm-agent"
    assert sanitize(ROOT_HERMES + "/skills") == "~/.hermes/skills"
    assert sanitize(ROOT_OPENCLAW + "/workspace") == "~/.openclaw/workspace"


def test_secret_file_names_and_tokens_redacted() -> None:
    assert sanitize(SECRET_FILE) == "<CONFIG_FILE>"
    assert sanitize(SECRET_YAML) == "<CONFIG_FILE>"
    assert sanitize(SECRET_TOKEN) == "<SECRET_REDACTED>"


def test_sanitize_is_idempotent() -> None:
    for sample in RED_LINE_TOKENS + [SECRET_TOKEN, "plain text"]:
        once = sanitize(sample)
        assert sanitize(once) == once


def test_sanitize_obj_redacts_secret_keys() -> None:
    payload = {"api_key": "value", "name": "demo-alpha", "nested": {"token": "x"}}
    result = sanitize_obj(payload)
    assert result["api_key"] == "<KEY_REDACTED>"
    assert result["nested"]["token"] == "<KEY_REDACTED>"
    assert result["name"] == "demo-alpha"


def test_sanitize_obj_redacts_sensitive_dict_keys() -> None:
    """Regression (QA S3): sensitive strings must not hide in *key* position."""
    payload = {SERVER_SAMPLE: "v", CHANNEL_A: "v", MARKET_A: "v", "name": "demo"}
    result = sanitize_obj(payload)
    joined = " ".join(str(key) for key in result)
    assert SERVER_SAMPLE not in joined
    assert CHANNEL_A not in joined
    assert MARKET_A not in joined
    assert result["name"] == "demo"


def test_version_prefixed_ipv4_is_redacted() -> None:
    """Regression (QA S3): v10.0.0.1 must not slip past the IPv4 gate.

    The octets are consumed by the gate; a single leading version letter may
    survive (it carries no location information).
    """
    result = sanitize("build v10." + "0.0." + "1 ok")
    assert "10.0.0.1" not in result
    assert "<SERVER>" in result


def test_hex_digest_and_uppercase_words_survive() -> None:
    """Regression (QA S3): over-redaction must not destroy legitimate content."""
    sha = "a" * 64
    assert sanitize(sha) == sha
    assert sanitize("OPENSOURCEALTERNATIVES") == "OPENSOURCEALTERNATIVES"
    assert sanitize("L" * 500) == "L" * 500
    assert sanitize("Bearer of good news") == "Bearer of good news"


def test_bearer_token_still_redacted() -> None:
    token = "Bearer " + "ab" + "c1" + "2" * 12
    assert sanitize(token) == "<SECRET_REDACTED>"


def test_repository_has_zero_red_line_hits() -> None:
    """Scan every repository text file for red-line tokens; expect no hits."""
    hits: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for token in RED_LINE_TOKENS:
            if token in text:
                hits.append(f"{path.relative_to(REPO_ROOT)}:{token}")
    assert hits == [], f"red-line tokens found: {hits}"
