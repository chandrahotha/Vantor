#!/usr/bin/env python3
"""Fail the build on mojibake in tracked text files.

`frontend/components/Shell.tsx` shipped every sidebar icon as mojibake
(three-times-encoded UTF-8 standing in for a single geometric glyph) because a
UTF-8 file was decoded as Windows-1252 and re-encoded, repeatedly. It compiled,
linted, typechecked and passed every test - the corruption is only visible in
the rendered sidebar, and only to a human looking at it. So it is checked here
instead.

Detection is deliberately narrow: it looks for the *characteristic pair* of a
mis-decoded UTF-8 string, not for non-ASCII characters. Legitimate content
(em dash, place-of-interest sign, arrows, ellipsis, e-acute) must never trip
this, and neither must a guard that flags its own help text. The examples in
this file are therefore written with escapes rather than as literal bytes.

Usage:  python scripts/check_mojibake.py [paths...]
Exit 1 with a file:line report when mojibake is found.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", ".next", "dist", "build", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".kilo", "uploads", "coverage", "venv", ".venv",
}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".pdf", ".zip", ".gz",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".pyc", ".db", ".sqlite3",
}
#: Characters that Windows-1252 puts where Unicode has nothing, plus the
#: Latin-1 supplement. Seeing one of these *immediately after* an
#: A-circumflex / A-tilde / A-grave is the exact signature of "UTF-8 was decoded
#: as cp1252 and re-encoded". No real prose contains that pair, which is what
#: keeps a legitimate em dash, ellipsis, curly quote or e-acute from tripping
#: this: those never follow an A-lead.
_REMAP = "\u0080-\u00bf\u2013\u2014\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f" \
         "\u2020\u2021\u2022\u2026\u2030\u2039\u203a\u0152\u0153\u0160\u0161" \
         "\u0178\u017d\u017e\u0192\u02c6\u02dc\u2122\u20ac"
#: Lead characters of a corrupted sequence: A-circumflex, A-tilde, A-grave.
_LEAD = "\u00c2\u00c3\u00e2\u00e3"

PATTERNS = [
    re.compile(f"[{_LEAD}][{_REMAP}]"),   # A-lead + cp1252 remap: the classic signature
    re.compile("[\u0080-\u009f]"),        # bare C1 control: always a decode bug
    re.compile("\ufffd"),                 # U+FFFD replacement character
]


def candidates(paths: list[str]) -> list[Path]:
    if paths:
        out: list[Path] = []
        for raw in paths:
            p = Path(raw)
            out.extend(p.rglob("*") if p.is_dir() else [p])
        return [p for p in out if p.is_file() and p.suffix.lower() not in SKIP_SUFFIXES]
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], capture_output=True, text=True, check=True
        ).stdout.split("\0")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("check_mojibake: git ls-files failed; pass explicit paths instead", file=sys.stderr)
        return []
    return [Path(f) for f in tracked if f and Path(f).suffix.lower() not in SKIP_SUFFIXES]


def scan(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    hits: list[tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), 1):
        if any(pat.search(line) for pat in PATTERNS):
            hits.append((n, line.strip()[:120]))
    return hits


def flagged(line: str) -> bool:
    return any(pat.search(line) for pat in PATTERNS)


#: Self-test. The first version of this guard shipped a pattern that missed the
#: single most common mojibake sequence (an A-tilde lead followed by U+20AC) and
#: reported the repository "clean" while four real cases were still in the tree.
#: A guard that cannot detect its own target is worse than none, so the corpus
#: lives here, is written with escapes (so the file does not flag itself), and
#: is asserted on every run.
MUST_FLAG = [
    "\u00e2\u20ac\u201d",               # double-encoded em dash
    "\u00c3\u2014",                     # double-encoded em dash, latin-1 flavour
    "\u00c2\u00a9",                     # copyright after an A-circumflex lead
    "\u00c2\u00ae",                     # registered sign after the same lead
    "\u00e2\u0086\u0098\u00e2\u0086\u009c",  # double-encoded up/down arrows
    "\u00e2\u0153\u02dc",               # double-encoded place-of-interest sign
    "\u00e2\u20ac\u00a6",               # double-encoded ellipsis
    "\u00e3\u0080\u0093",               # double-encoded macron
    "replacement \ufffd here",          # U+FFFD
    "bare \u008f control",              # raw C1 control
]
MUST_NOT_FLAG = [
    "A clean em dash \u2014 and an ellipsis \u2026",
    "Curly quotes \u2018single\u2019 and \u201cdouble\u201d",
    "Ctrl/\u2318+K then \u2191\u2193 to move and \u21b5 to open",
    "Sidebar glyphs \u25c8 \u25c9 \u25c7 \u25a3 \u25eb \u25ec \u25a4 \u2733 and \u2600 \u263e",
    "Search with \u2315",
    "caf\u00e9 na\u00efve \u00e9t\u00e9 r\u00e9sum\u00e9 \u2014 El ni\u00f1o comi\u00f3 jam\u00f3n",
    "n\u00e3o \u00e3o irm\u00e3 ning\u00fem",
    "Agpl-3.0 and a plain hyphen-dash",
    "source \u00b7 AGPL",
]


def self_test() -> int:
    failures: list[str] = []
    for s in MUST_FLAG:
        if not flagged(s):
            failures.append(f"MUST FLAG but did not: {s!r}")
    for s in MUST_NOT_FLAG:
        if flagged(s):
            failures.append(f"MUST NOT FLAG but did: {s!r}")
    if failures:
        print("check_mojibake: SELF-TEST FAILED — the pattern no longer detects "
              "what it exists to detect:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    if self_test():
        return 1
    files = candidates(argv)
    findings: list[tuple[Path, int, str]] = []
    for path in files:
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        for n, line in scan(path):
            findings.append((path, n, line))
    if not findings:
        print(f"check_mojibake: clean ({len(files)} files scanned, "
              f"{len(MUST_FLAG) + len(MUST_NOT_FLAG)} self-test cases passed)")
        return 0
    print(f"check_mojibake: {len(findings)} mis-encoded line(s):", file=sys.stderr)
    for path, n, line in findings:
        print(f"  {path.as_posix()}:{n}: {line}", file=sys.stderr)
    print(
        "\nA file was decoded as Windows-1252 and re-encoded as UTF-8. Fix by\n"
        "editing the line with the intended character (often an em dash, box\n"
        "drawing glyph or an arrow) — do not re-encode the whole file.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
