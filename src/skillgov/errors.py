"""Error types, exit codes and degradation reasons for skillgov."""

from __future__ import annotations


class SkillgovError(Exception):
    """Base class for all skillgov errors."""


class ConfigError(SkillgovError):
    """Invalid configuration (unknown format, malformed option value, ...)."""


class ReadOnlyViolation(SkillgovError):
    """The read-only guard detected a write or an unexpected mutation."""


class DegradeReason:
    """Canonical, machine-readable reasons for graceful degradation.

    Any collection anomaly is recorded with one of these reasons instead of
    raising, so a single missing/broken source never aborts a run.
    """

    MISSING_ROOT = "missing_root"
    MISSING_SKILLS_DIR = "missing_skills_dir"
    MISSING_USAGE_JSON = "missing_usage_json"
    MISSING_STATE_DB = "missing_state_db"
    MISSING_STORE_LOCK = "missing_store_lock"
    MISSING_TRAJECTORY = "missing_trajectory"
    BAD_JSON = "bad_json"
    BAD_JSONL = "bad_jsonl"
    EMPTY_DIR = "empty_dir"
    EMPTY_USAGE_LOG = "empty_usage_log"
    TRUNCATED_INPUT = "truncated_input"
    NO_SOURCES = "no_sources"


# Exit codes (see README / design section 4).
EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_CLI = 2
EXIT_NO_SOURCE = 3
