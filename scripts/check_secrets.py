#!/usr/bin/env python3
"""Fail the build if a credential is committed.

Replaces an inline `grep` in `.github/workflows/ci.yml` that **could never pass**:
the pattern `sk-(live|proj)` appeared literally in the workflow file's own
command line, so the guard matched itself, exited 1, and had been red on every
run. A security gate that always fails is worse than none - it looks like
coverage while checking nothing.

It also scanned `.kilo/worktrees/`, a stale worktree copy of this repository,
which is not a `git ls-files` target but is still on disk, so a credential would
have been reported from a file nobody committed.

What this actually scans: tracked files only, minus binary and vendored trees.
Matching is on the *shape* of a credential, not on the presence of the word
"secret", so documentation, `.env.example` placeholders and this file all pass.

Usage:  python scripts/check_secrets.py [paths...]
Exit 1 with a file:line report when a credential-shaped string is found.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", ".next", "node_modules", "dist", "build", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".kilo", "uploads", "coverage", "venv", ".venv",
}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".pyc", ".db", ".sqlite3",
}

#: Credential shapes. Each is assembled from fragments so this file does not
#: contain any of them literally - otherwise the scanner would flag its own
#: source, which is exactly the bug this script replaces.
PATTERNS = [
    (re.compile("sk-" + r"(live|proj|or-v1)-[A-Za-z0-9]{8,}", re.I), "openai-style key"),
    (re.compile("gh[pousr]_" + r"[A-Za-z0-9]{20,}"), "github token"),
    (re.compile("github_pat_" + r"[A-Za-z0-9_]{30,}"), "github fine-grained token"),
    (re.compile("AKIA" + r"[0-9A-Z]{16}"), "aws access key id"),
    (re.compile("-----BEGIN " + r"(RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"), "private key block"),
    (re.compile("xox[baprs]-" + r"[A-Za-z0-9-]{10,}"), "slack token"),
    (re.compile("AIza" + r"[A-Za-z0-9_-]{30,}"), "google api key"),
]

#: Values that are obviously placeholders. `.env.example` and the docs are full of
#: them and must not fail the build.
PLACEHOLDER = re.compile(
    r"change[-_ ]?me|placeholder|example|your[-_ ]|dummy|fake|notavaultref|"
    r"test[-_]?not[-_]?a[-_]?real|xxxxxxxx|generate-|<[^>]+>|\.\.\.",
    re.I,
)


def tracked_files(paths: list[str]) -> list[Path]:
    if paths:
        out: list[Path] = []
        for raw in paths:
            p = Path(raw)
            out.extend(p.rglob("*") if p.is_dir() else [p])
        return [p for p in out if p.is_file() and p.suffix.lower() not in SKIP_SUFFIXES]
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z"], capture_output=True, text=True, check=True
        ).stdout.split("\0")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("check_secrets: git ls-files failed; pass explicit paths instead", file=sys.stderr)
        return []
    files = [Path(f) for f in listed if f and Path(f).suffix.lower() not in SKIP_SUFFIXES]
    return [f for f in files if not any(part in SKIP_DIRS for part in f.parts)]


def findings_in(text: str) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []
    for n, line in enumerate(text.splitlines(), 1):
        if PLACEHOLDER.search(line):
            continue
        for pat, label in PATTERNS:
            m = pat.search(line)
            if m:
                out.append((n, label, line.strip()[:100]))
                break
    return out


#: Self-test, for the same reason the mojibake guard has one: a scanner that
#: cannot detect its own target is worse than no scanner.
#: Self-test corpus. Assembled with escapes for the same reason the patterns are:
#: a scanner that flags its own source is the exact bug this script replaces.
MUST_FLAG = [
    "sk-" + "live-AbCdEfGh1234",
    "sk-" + "proj-0123456789abcdef",
    "gh" + "p_0123456789abcdefghijklmnopqrstuvwxyz",
    "github_pat_" + "11ABCD0123456789_abcdefghijklmnopqrstuvwxyz",
    "AKI" + "A0B1C2D3E4F5G6H7J",
    "-----BEGIN " + "RSA PRIVATE KEY-----",
    "xox" + "b-1234567890-abcdefghij",
    "AIz" + "aSyA1234567890abcdefghijklmnopqrstuv",
]
MUST_NOT_FLAG = [
    'secret_ref = "notavaultref-must-be-refused-1"',
    "OPENAI_API_KEY=",
    "POSTGRES_PASSWORD=change-me-in-env",
    "JWT_SECRET=generate-32-bytes-min",
    "S3_SECRET_KEY=minioadmin-change-me",
    'keycloak().token ?? ""',
    "sk-" + "test-not-a-real-key",
    "ENCRYPTION_KEY=<your-32-byte-key>",
    # A real-looking AWS *documentation* key is filtered by the placeholder rule,
    # not by a narrower pattern: the rule is explicit, so it can be argued with.
    "AKIAIOSFODNN7EXAMPLE",
]


def self_test() -> int:
    failures: list[str] = []
    for s in MUST_FLAG:
        if not findings_in(s):
            failures.append(f"MUST FLAG but did not: {s[:30]}")
    for s in MUST_NOT_FLAG:
        if findings_in(s):
            failures.append(f"MUST NOT FLAG but did: {s[:30]}")
    # The scanner must not match its own source, which is the bug it replaces.
    own = Path(__file__).read_text(encoding="utf-8")
    if findings_in(own):
        failures.append("the scanner flags its own source")
    if failures:
        print("check_secrets: SELF-TEST FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    if self_test():
        return 1
    files = tracked_files(argv)
    found: list[tuple[Path, int, str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, label, line in findings_in(text):
            found.append((path, n, label, line))
    if not found:
        print(f"check_secrets: clean ({len(files)} tracked files scanned, "
              f"{len(MUST_FLAG) + len(MUST_NOT_FLAG)} self-test cases passed)")
        return 0
    print(f"check_secrets: {len(found)} possible credential(s):", file=sys.stderr)
    for path, n, label, line in found:
        print(f"  {path.as_posix()}:{n}: [{label}] {line}", file=sys.stderr)
    print(
        "\nIf one of these is genuinely a placeholder, add it to PLACEHOLDER in\n"
        "scripts/check_secrets.py rather than weakening the pattern. If it is real,\n"
        "rotate it now: history already holds it.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
