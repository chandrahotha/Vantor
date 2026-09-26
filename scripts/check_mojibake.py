#!/usr/bin/env python3
"""Fail the build on mojibake in tracked text files.

`frontend/components/Shell.tsx` shipped every sidebar icon as mojibake
(`Ã¢â€”Ë†` instead of `◈`) because a UTF-8 file was decoded as Windows-1252 and
re-encoded, repeatedly. It compiled, linted, typechecked and passed every test —
the corruption is only visible in the rendered sidebar, and only to a human
looking at it. So it is checked here instead.

Detection is deliberately narrow: it looks for the *characteristic* byte
sequences of a mis-decoded UTF-8 string, not for non-ASCII characters. Legitimate
content (`—`, `⌘`, `↑↓`, `…`, `é`) must never trip this.

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
#: Sequences that only appear when UTF-8 was decoded as cp1252/latin-1 and
#: re-encoded. Each is a multi-byte run, not a single accented letter.
PATTERNS = [
    re.compile("[\u00c2\u00c3][\u0080-\u00bf\u2018-\u201f\u20ac\u2122]"),  # Ã‚ Ã¢â € Â©
    re.compile("\u00e2[\u0080-\u009f\u201a\u201e\u2020\u2026]"),               # â€ â„ â€¦
    re.compile("\ufffd"),                                                       # U+FFFD
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


def main(argv: list[str]) -> int:
    files = candidates(argv)
    findings: list[tuple[Path, int, str]] = []
    for path in files:
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        for n, line in scan(path):
            findings.append((path, n, line))
    if not findings:
        print(f"check_mojibake: clean ({len(files)} files scanned)")
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
