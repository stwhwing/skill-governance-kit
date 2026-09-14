# skill-governance-kit (`skillgov`)

A **read-only, deterministic** toolkit for auditing AI-agent *skill* ecosystems.
It answers the questions that a skill zoo always raises: what do I have, what is
actually used, where did each skill come from, and which skills are mirrored
across two agents?

`skillgov` currently understands three ecosystems — **Hermes**, **OpenClaw** and
**WorkBuddy** — and normalizes them into a single, comparable schema. It never
writes to the trees it inspects; writing actions are explicitly out of scope.

## Why it is safe to run on production hosts

- **Read-only by construction.** Files are only ever opened in `"r"` mode and
  SQLite only through a `mode=ro` URI. A `readonly` guard snapshots the inspected
  roots before and after a run and asserts a **zero-write** outcome.
- **Zero runtime dependencies.** Standard library only (Python ≥ 3.11). No
  PyYAML, no third-party packages — easy to audit, easy to ship.
- **One redaction gate.** Every outward-facing string passes through
  `skillgov.sanitize.sanitize()` / `sanitize_obj()`. There is no bypass.
- **Deterministic & idempotent.** Two runs over the same input produce
  byte-identical JSON, except for a single `generated_at` field. A stable
  `records.json` (the normalized store artifact) carries no timestamp at all.
- **Degrades, never crashes.** A missing usage file, a malformed JSONL line or an
  empty directory is recorded in `RunResult.warnings` and echoed to stderr; the
  run still finishes.

## Install

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .
```

No runtime dependencies are pulled in. Optional developer tooling lives in the
`dev` extra:

```bash
pip install -e ".[dev]"         # pytest, ruff, mypy
```

## Quickstart

```bash
# 1. Full inventory of both ecosystems
skillgov inventory --hermes-root ~/hm --openclaw-root ~/oc --out out --format md,json

# 2. Usage, restricted to a time window
skillgov usage --hermes-root ~/hm --openclaw-root ~/oc --since 2025-01-01

# 3. A single skill's provenance card
skillgov card hermes:demo-alpha --hermes-root ~/hm --openclaw-root ~/oc

# 4. Cross-ecosystem mirror comparison
skillgov mirror --hermes-root ~/hm --openclaw-root ~/oc

# 5. Everything at once
skillgov report --hermes-root ~/hm --openclaw-root ~/oc --out out --format md,json
```

Roots are always configurable; reports only ever contain paths *relative to a
root*, never an absolute machine location.

## Caliber declaration (口径声明)

These definitions are injected into the report footer for **each ecosystem
covered by the run**; the WorkBuddy line therefore appears only when the
WorkBuddy ecosystem is part of the run (its `skills` directory exists, so
`workbuddy` enters `RunResult.sources` — independently of whether any record or
a usable ledger was produced). They are part of the contract:

- **Hermes usage** = `skill_view` standard loading. Direct file reads
  (`read_file`) and terminal access are **not** counted.
- **OpenClaw usage** = the *strict* caliber only: a trajectory tool call whose
  `arguments.path` points at a `skills/<name>/SKILL.md`. Plain references inside
  message bodies are recorded as corroboration (旁证) and never inflate
  `use_count`.
- **OpenClaw session-snapshot catalogs** (the `skills.entries` listing embedded
  in a trajectory) are **never** counted as usage.
- **WorkBuddy usage** (v0.2) = the number of *usage days* in the
  `usage-log.json` ledger (`len(recentDates)`) — **counted in days, not in
  invocation times**. The ledger does not track views or patches, so
  `view_count` / `patch_count` stay `0`. Ledger keys that match no skill
  directory are reported as `orphan_ledger_entry` warnings and produce no
  record.
- **WorkBuddy 口径声明（第 6 条）**：`use_count` = `usage-log.json` 台账
  `recentDates` 的**使用天数**（**按使用天数计**，非调用次数）；台账不跟踪
  view/patch，故 `view_count` / `patch_count` 恒为 `0`；`last_used_at` =
  `lastUsedDate` 当日 `00:00:00Z`；台账键在技能树中无对应目录者记
  `orphan_ledger_entry` 告警且不生成记录。
- **Read-only**: missing sources degrade with a recorded reason.

## WorkBuddy (v0.2)

WorkBuddy support is **opt-in**: passing `--workbuddy-root <root>` adds the
ecosystem to the run; omitting it keeps the output byte-identical to a
Hermes+OpenClaw-only run.

- **Inventory**: `<workbuddy-root>/skills/**/SKILL.md` is walked recursively.
  Non-skill auxiliary entries (segments starting with `_`) and backup
  directories (`*.bak-*`) are skipped; the shared archive markers (`.archive/`,
  `*.archived`) mark a skill `archived`.
- **Archive matching is per path segment** (Hermes, OpenClaw and WorkBuddy use
  the same rule): a segment must *equal* `.archive` or *start with* `.archived`,
  so a legitimate directory such as `plain.archive-helper` stays `active` —
  raw substring matching is deliberately not used.
- **Usage**: the first-hand ledger `<workbuddy-root>/usage-log.json` maps
  ledger keys (skill directory names) to `firstSeenDate` / `recentDates` /
  `lastUsedDate`. See caliber item 6 above for the exact mapping; the ledger is
  a first-hand source, so `confidence` is always `A`. `provenance()` reuses the
  same filtered mapping as `usage()`, so a `type != "skill"` entry or an orphan
  key never attaches evidence to a skill whose usage stays `none`.
- **Scope boundary**: v0.2 covers the *user skills directory only*. Parsing of
  `audit-log/*.jsonl` (a potential corroboration source) and the
  `plugins/cache` / `connectors` trees is deliberately deferred.
  （v0.2 边界：仅覆盖用户技能目录，不含 `plugins/cache` 与 `connectors`；
  `audit-log/*.jsonl` 解析留待后续，作为旁证源。）

## Continuous integration

`.github/workflows/ci.yml` runs the full test suite on every push and pull
request across a matrix of `ubuntu-latest` / `windows-latest` and Python
3.11 / 3.13. Only `pytest` is installed — the project itself has zero runtime
dependencies, so CI stays fast and hermetic:

```bash
python -m pip install pytest
python -m pytest -q
```

## The `--assert-readonly` switch

The collector is read-only by construction. `--assert-readonly` adds a
defence-in-depth guarantee: every configured root is fingerprinted (file
count + bytes + `<relpath, size, mtime>` digest) before and after the run, and
any difference aborts with exit code 1 (an integrity violation is treated as an
internal error, not a degradation).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success (including a run that degraded *with a reason*) |
| 1 | unexpected internal error |
| 2 | CLI argument error |
| 3 | no usable data source at all |

## Architecture

A five-layer, read-only pipeline with a small adapter boundary, so a new
ecosystem can be added by implementing one protocol:

```
             +------------------------------------------------------+
             |                        cli                           |
             |   argparse -> config -> adapters -> merge -> report  |
             +------------------------------------------------------+
                |            |             |            |
        +-------+---+  +-----+------+  +---+-----+  +---+------+
        | adapters  |  | normalize  |  |  store  |  |  report  |
        | fs_scan   |  | model      |  | ids     |  | inventory|
        | hermes    |  | merge      |  | json    |  | usage    |
        | openclaw  |  | (mirror /  |  | store   |  | card     |
        | trajectory|  |  drift)    |  |         |  | mirror   |
        +-----------+  +------------+  +---------+  | render   |
                                                    +----------+
   cross-cutting:  sanitize (single redaction gate)  |  readonly (zero-write guard)
```

- **adapters** — read-only collection per ecosystem, emitting raw evidence.
- **normalize** — merge to `SkillRecord`, attach usage/provenance, pair mirrors,
  judge drift.
- **store** — stable `skill_id` derivation and atomic, deterministic JSON.
- **report** — four views (inventory / usage / card / mirror), rendered to md
  and json.
- **cli** — subcommands, options and exit codes.

### File layout

```
src/skillgov/
  __init__.py  __main__.py  config.py  errors.py  logging_setup.py
  sanitize.py  readonly.py
  adapters/    base.py  fs_scan.py  hermes.py  openclaw.py  trajectory.py
  normalize/   model.py  merge.py
  store/       ids.py  json_store.py
  report/      inventory.py  usage.py  card.py  mirror.py  render.py
  cli/         main.py
tests/         conftest.py  fixtures/**  test_*.py
examples/      fixtures/**  out/**
```

## Data model (excerpt)

```python
@dataclass(frozen=True)
class SourceEvidence:
    kind: str            # store_lock | generated_from | curator | trajectory_mention | birth
    detail: str          # already-safe text
    observed_at: str | None

@dataclass
class UsageRecord:
    use_count: int = 0
    view_count: int = 0
    patch_count: int = 0
    last_used_at: str | None = None
    state: str | None = None
    evidence_source: str = "none"   # usage_json | state_db | trajectory | none
    confidence: str = "C"           # "A" first-hand / "C" inferred

@dataclass
class SkillRecord:
    skill_id: str        # f"{ecosystem}:{rel_path_slug}"
    name: str
    ecosystem: str       # hermes | openclaw
    path: str            # relative to the configurable root
    presence: str        # active | archived
    category: str
    ...
    mirror_of: str | None
    drift: str | None    # clean | differs | unknown
```

## Redaction rules

The gate removes, at minimum: IPv4 addresses, known distribution/marketplace
domains, channel/group identifiers (known prefixes and long base32/base64
tokens), secret-like tokens (API keys, GitHub/AWS tokens, PEM headers, bearer
credentials), secret file names, internal nicknames and real absolute roots.
Replacements are stable placeholders such as `<SERVER>`, `<MARKETPLACE>`,
`<CHANNEL_ID>`, `<SECRET_REDACTED>`, `<CONFIG_FILE>`.

To keep the repository itself clean, the sensitive literals used by the gate are
assembled from fragments in source, and a test scans every repository file to
assert **zero** red-line hits.

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q
```

The suite covers the filesystem scanner, all three adapters (including the
trajectory container split and the WorkBuddy ledger caliber), the redaction
gate, the read-only guard (including `--assert-readonly`), all four report views
and the CLI end-to-end (subcommands, idempotency and exit codes). Fixtures are
synthetic only: `demo-*` / `wb-*` skill names and fixed timestamps.

## License

MIT — see [LICENSE](LICENSE).
