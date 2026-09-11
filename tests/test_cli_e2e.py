"""End-to-end CLI tests: subcommands, idempotency, exit codes, subprocess runs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from skillgov.cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"


def _run_subprocess(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run(
        [sys.executable, "-m", "skillgov", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


def _strip_generated(payload: dict) -> dict:
    payload = dict(payload)
    payload.pop("generated_at", None)
    return payload


def test_all_subcommands_produce_files(hermes_root, openclaw_root, tmp_path) -> None:
    out = tmp_path / "out"
    common = [
        "--hermes-root",
        str(hermes_root),
        "--openclaw-root",
        str(openclaw_root),
        "--out",
        str(out),
        "--format",
        "md,json",
    ]

    assert main(["inventory", *common]) == 0
    assert (out / "inventory.md").is_file()
    assert (out / "inventory.json").is_file()

    assert main(["usage", *common, "--since", "2025-01-01"]) == 0
    assert (out / "usage.md").is_file()

    assert main(["mirror", *common]) == 0
    assert (out / "mirror.json").is_file()

    assert main(["card", "hermes:demo-alpha", *common]) == 0
    assert (out / "card-hermes-demo-alpha.md").is_file()

    assert main(["report", *common]) == 0
    for name in ("inventory", "usage", "mirror", "report"):
        assert (out / f"{name}.md").is_file()
        assert (out / f"{name}.json").is_file()


def test_inventory_counts(hermes_root, openclaw_root, tmp_path) -> None:
    out = tmp_path / "out"
    main(
        [
            "inventory",
            "--hermes-root",
            str(hermes_root),
            "--openclaw-root",
            str(openclaw_root),
            "--out",
            str(out),
            "--format",
            "json",
        ]
    )
    payload = json.loads((out / "inventory.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == 5
    assert payload["summary"]["active"] == 4
    assert payload["summary"]["archived"] == 1


def test_json_output_is_idempotent(hermes_root, openclaw_root, tmp_path) -> None:
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    common = [
        "--hermes-root",
        str(hermes_root),
        "--openclaw-root",
        str(openclaw_root),
        "--format",
        "json",
    ]
    assert main(["report", *common, "--out", str(out_a)]) == 0
    assert main(["report", *common, "--out", str(out_b)]) == 0

    for name in ("inventory", "usage", "mirror", "report"):
        first = json.loads((out_a / f"{name}.json").read_text(encoding="utf-8"))
        second = json.loads((out_b / f"{name}.json").read_text(encoding="utf-8"))
        assert _strip_generated(first) == _strip_generated(second), name


def test_exit_code_no_data_source(tmp_path) -> None:
    assert main(["inventory", "--out", str(tmp_path / "out")]) == 3


def test_exit_code_bad_format(hermes_root, tmp_path) -> None:
    assert (
        main(
            [
                "inventory",
                "--hermes-root",
                str(hermes_root),
                "--format",
                "xml",
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 2
    )


def test_exit_code_bad_since(hermes_root, tmp_path) -> None:
    assert (
        main(
            [
                "usage",
                "--hermes-root",
                str(hermes_root),
                "--since",
                "not-a-date",
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 2
    )


def test_exit_code_card_not_found(hermes_root, tmp_path) -> None:
    assert (
        main(
            [
                "card",
                "hermes:missing",
                "--hermes-root",
                str(hermes_root),
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 2
    )


def test_degenerate_roots_do_not_crash(degenerate_root, tmp_path) -> None:
    out = tmp_path / "out"
    code = main(
        [
            "report",
            "--hermes-root",
            str(degenerate_root / "hermes-root"),
            "--openclaw-root",
            str(degenerate_root / "openclaw-root"),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    joined = " ".join(report["warnings"])
    assert "missing_usage_json" in joined
    assert "bad_jsonl" in joined


def test_degenerate_empty_root_exit_three(degenerate_root, tmp_path) -> None:
    code = main(
        [
            "inventory",
            "--hermes-root",
            str(degenerate_root / "empty"),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert code == 3


def test_subprocess_version_and_run(hermes_root, openclaw_root, tmp_path) -> None:
    version = _run_subprocess(["--version"], REPO_ROOT)
    assert version.returncode == 0
    assert "0.1.0" in (version.stdout + version.stderr)

    run = _run_subprocess(
        [
            "inventory",
            "--hermes-root",
            str(hermes_root),
            "--openclaw-root",
            str(openclaw_root),
            "--out",
            str(tmp_path / "out"),
            "--format",
            "json",
        ],
        REPO_ROOT,
    )
    assert run.returncode == 0
    assert (tmp_path / "out" / "inventory.json").is_file()
