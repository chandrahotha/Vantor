#!/usr/bin/env python3
"""Derive the project's surface counts, and check the docs against them.

VNT-042. The documentation asserted hand-written numbers, and they had drifted
into contradicting each other inside a single repository:

    README.md            68 operations, 156 pytest, 35 vitest
    backend/README.md    75 operations across 64 paths, 96 pytest
    frontend/README.md   9 routes, 12 of 75 operations, 0 frontend tests

Three files, three different answers, none of them true. A count in prose is a
claim that decays silently: adding a route changes reality, nothing changes the
sentence, and the only signal is a reader noticing. This script is the signal.

It derives the numbers from the artifacts that define them:

    operations, paths   api/openapi.json (generated from the app)
    backend tests       pytest --collect-only
    frontend tests      vitest
    frontend routes     a page.tsx per route, on disk

and `--check` fails when a document disagrees, so the drift is caught on the
push that causes it rather than by a reader noticing months later.

Usage:
    python scripts/doc_counts.py            # print the truth
    python scripts/doc_counts.py --check    # fail if the docs disagree
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The badge in README.md is generated from `operations` by hand, so it is
#: checked by the "API: N operations" prose pattern below. Kept here as a record
#: of intent rather than as a second source of truth.

#: Prose patterns per document. Each must contain a `{n}` for the number the
#: check substitutes; a pattern that no longer matches its document is itself
#: reported, so a rewrite of the wording cannot quietly disable the gate.
PROSE: dict[str, list[str]] = {
    "README.md": [
        r"API[:\s]+(\d+)\s+operations",
        r"(\d+)\s+pytest\s+green",
        r"(\d+)\s+vitest\s+green",
    ],
    "backend/README.md": [
        r"(\d+)\s+API\s+operations",
        r"(\d+)\s+pytest\s+green",
    ],
    "frontend/README.md": [
        r"(\d+)\s+routes",
        r"(\d+)\s+vitest\s+green",
    ],
}


def _run(cmd: list[str], cwd: pathlib.Path) -> str:
    # Resolve argv[0] to a real path. On Windows `shutil.which("npx")` answers
    # `npx.CMD`, but exec'ing the bare name "npx" still fails with WinError 2, so
    # the *resolved* path has to be what is passed to subprocess. Getting this
    # wrong makes the script report "could not run" rather than the real count,
    # which is worse than not having the script.
    if cmd:
        resolved = shutil.which(cmd[0])
        if resolved is None:
            for suffix in (".cmd", ".exe", ".bat", ".CMD"):
                if shutil.which(cmd[0] + suffix):
                    resolved = shutil.which(cmd[0] + suffix)
                    break
        if resolved is None:
            print(f"warning: {cmd[0]} is not on PATH", file=sys.stderr)
            return ""
        cmd = [resolved, *cmd[1:]]
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=900, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"warning: could not run {' '.join(cmd)}: {exc}", file=sys.stderr)
        return ""
    return proc.stdout + proc.stderr


def counts() -> dict[str, int | None]:
    out: dict[str, int | None] = {}

    # API surface, from the generated contract rather than from the code, so the
    # number is the one a client would actually see.
    spec_path = ROOT / "api" / "openapi.json"
    if spec_path.exists():
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        paths = spec.get("paths", {})
        out["paths"] = len(paths)
        out["operations"] = sum(
            1
            for methods in paths.values()
            for method in methods
            if method in {"get", "post", "put", "patch", "delete"}
        )
    else:
        out["paths"] = out["operations"] = None

    out["backend_tests"] = _collect_backend()
    out["frontend_tests"] = _collect_frontend()
    out["frontend_routes"] = len(list((ROOT / "frontend" / "app").rglob("page.tsx")))
    return out


def _collect_backend() -> int | None:
    output = _run(
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q",
         "-p", "no:randomly"],
        ROOT / "backend",
    )
    match = re.search(r"(\d+)\s+tests? collected", output)
    return int(match.group(1)) if match else None


def _collect_frontend() -> int | None:
    output = _run(["npx", "vitest", "run"], ROOT / "frontend")
    match = re.search(r"Tests\s+(\d+)\s+(?:passed|failed)", output)
    return int(match.group(1)) if match else None


def check(c: dict[str, int | None]) -> int:
    problems: list[str] = []
    for doc, patterns in PROSE.items():
        path = ROOT / doc
        if not path.exists():
            problems.append(f"{doc}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                # A pattern that no longer matches means the sentence was
                # reworded, so the gate is now checking nothing for that claim.
                problems.append(
                    f"{doc}: no sentence matches {pattern!r} — the count is no "
                    "longer stated, or was reworded; update PROSE in this script "
                    "so the gate keeps working"
                )
                continue
            stated = int(match.group(1))
            key = _key_for(doc, pattern)
            actual = c.get(key)
            if actual is None:
                problems.append(f"{doc}: could not determine {key}")
            elif stated != actual:
                problems.append(
                    f"{doc}: says {stated} for {key}, reality is {actual} "
                    f"(pattern {pattern!r})"
                )
    for p in problems:
        print(f"FAIL {p}", file=sys.stderr)
    if problems:
        return 1
    print("documentation counts match the code")
    return 0


def _key_for(doc: str, pattern: str) -> str:
    if "operations" in pattern:
        return "operations"
    if "pytest" in pattern:
        return "backend_tests"
    if "vitest" in pattern:
        return "frontend_tests"
    if "routes" in pattern:
        return "frontend_routes"
    if "paths" in pattern:
        return "paths"
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if the documentation disagrees with the code")
    args = parser.parse_args()

    c = counts()
    for key, value in c.items():
        print(f"{key:16} {value}")
    if args.check:
        print()
        return check(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
