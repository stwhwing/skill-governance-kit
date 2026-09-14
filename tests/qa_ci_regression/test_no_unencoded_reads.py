# -*- coding: utf-8 -*-
"""Regression guard: test code must read text with explicit UTF-8 encoding.

Windows CI runners default to cp1252; reading UTF-8 fixtures (which contain
Chinese caliber-footnote text) without ``encoding=`` raises UnicodeDecodeError.
This static scan fails the build if any test regresses to an un-encoded read or
to a ``subprocess.run(..., text=True)`` without ``encoding=``.
"""
import re
import pathlib

TESTS_DIR = pathlib.Path(__file__).resolve().parents[1]


def _call_span(src: str, start: int) -> str:
    """Return the substring of the call starting at `start` (at an opening paren)."""
    i = src.index("(", start)
    depth = 0
    j = i
    while j < len(src):
        ch = src[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1
    return src[start:]


def test_all_text_reads_use_explicit_encoding():
    offenders = []
    for py in sorted(TESTS_DIR.rglob("*.py")):
        if ".venv" in py.parts or "__pycache__" in py.parts:
            continue
        # Skip this very guard file: it contains regex literals and docstrings
        # that legitimately mention `read_text(` / `subprocess.run(..., text=True)`.
        if py.name == "test_no_unencoded_reads.py":
            continue
        src = py.read_text(encoding="utf-8")
        # 1) *.read_text(...) must carry encoding=
        for m in re.finditer(r"\.read_text\(", src):
            i = src.index("(", m.start())
            depth = 0
            j = i
            while j < len(src):
                if src[j] == "(":
                    depth += 1
                elif src[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            call = src[m.start():j + 1]
            if "encoding=" not in call:
                offenders.append("%s: unencoded read_text() -> %r"
                                 % (py.relative_to(TESTS_DIR), call[:60]))
        # 2) subprocess.run(..., text=True, ...) must carry encoding=
        for m in re.finditer(r"subprocess\.run\(", src):
            span = _call_span(src, m.start())
            if "text=True" in span and "encoding=" not in span:
                offenders.append("%s: subprocess.run(text=True) without encoding= -> %r"
                                 % (py.relative_to(TESTS_DIR), span[:80]))
    assert not offenders, "Un-encoded text reads found:\n" + "\n".join(offenders)
