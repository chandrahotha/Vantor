#!/usr/bin/env python3
"""Run a test tier and fail if it did not actually test anything.

pytest and vitest exit 0 when they select nothing and when they skip everything.
Both are defensible defaults for a *library* and both are wrong for a *tier* —
a tier exists to prove one thing, and "0 tests ran, all skipped" proves nothing
while looking green in the same column as a real pass. This repo has been bitten
by exactly that shape three times:

* the Postgres tier could not reach its service container and skipped, so the
  weekly full-suite run reported success without ever exercising row-level
  security;
* the worker's Redis tests skipped for the same reason and had never run
  anywhere, which is how the scheduler that crashes on boot stayed in the tree;
* `-m pg` selecting nothing (a lost marker) exits 5 for pytest, but a marker that
  survives while the tests under it lose their assertions exits 0.

`run_tier.py` is the one place that turns "this tier ran" into a requirement, so
CI and the Makefile assert it with the same command instead of each carrying its
own copy of the grep.

Usage:
    python scripts/run_tier.py --min-passed 9 --name "Postgres tier" -- python -m pytest -m pg -q
    python scripts/run_tier.py --min-passed 1 --name "e2e" --allow-fail -- npx playwright test
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

#: pytest's terminal summary, e.g. `383 passed, 9 skipped, 1 warning in 79.37s`.
PYTEST_COUNTS_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|deselected|xfailed|xpassed)")
#: pytest's nothing-selected line, which is the one that still exits non-zero but
#: for a reason a reader can mistake for a flake.
PYTEST_NO_TESTS_RE = re.compile(r"no tests ran")

#: vitest's summary block:
#:   Tests  170 passed (170)
#:   Tests  168 passed | 2 skipped (170)
#:   Test Files  14 passed (14)
VITEST_LINE_RE = re.compile(r"^\s*Tests\s+(.*)$", re.MULTILINE)
VITEST_COUNTS_RE = re.compile(r"(\d+) (passed|failed|skipped|todo|flaky)")


def parse_pytest(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    # Only the final summary line matters: pytest also prints per-skip reasons
    # like `SKIPPED [1] path::test: reason`, and those must not be counted.
    summary = next(
        (line for line in reversed(text.splitlines())
         if re.search(r"\d+ (passed|failed|skipped|error)", line) or PYTEST_NO_TESTS_RE.search(line)),
        "",
    )
    for value, kind in PYTEST_COUNTS_RE.findall(summary):
        counts[kind.rstrip("s") if kind != "errors" else "error"] = int(value)
    return counts


def parse_vitest(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    match = VITEST_LINE_RE.search(text)
    if not match:
        return counts
    for value, kind in VITEST_COUNTS_RE.findall(match.group(1)):
        counts[kind] = int(value)
    return counts


def parse(command: list[str], text: str, fmt: str = "auto") -> dict[str, int]:
    """Pick the parser. `auto` reads the command; pass `--format` when the command
    hides it (`npm run test:e2e` shells out to Playwright, and a wrapper that
    guesses from the command line would read that output as vitest)."""
    joined = " ".join(command)
    if fmt == "playwright" or (fmt == "auto" and "playwright" in joined):
        return {"passed": len(re.findall(r"^\s+\d+ \S+ .*»", text, re.MULTILINE)) or
                sum(int(n) for n in re.findall(r"(\d+) passed", text))}
    if fmt == "pytest" or (fmt == "auto" and "pytest" in joined):
        return parse_pytest(text)
    if fmt == "vitest":
        return parse_vitest(text)
    return parse_vitest(text)


#: (command, output, expected counts). Every parser branch has a case, because a
#: parser that only ever saw its happy path is how a tier goes green on zero tests.
SELF_TESTS: list[tuple[list[str], str, dict[str, int]]] = [
    (
        ["python", "-m", "pytest", "-m", "pg", "-q"],
        (
            "SKIPPED [1] tests/x.py:9: PG_TEST_DATABASE_URL is not set\n"
            "2 passed, 9 skipped, 381 deselected, 1 warning in 0.93s\n"
        ),
        {"passed": 2, "skipped": 9, "deselected": 381},
    ),
    (
        ["python", "-m", "pytest", "tests", "-q"],
        "383 passed, 9 skipped, 1 warning in 79.37s (0:01:19)\n",
        {"passed": 383, "skipped": 9},
    ),
    (
        ["python", "-m", "pytest", "-m", "pg", "-q"],
        "no tests ran in 0.09s\n",
        {},
    ),
    (
        ["python", "-m", "pytest", "-q"],
        "1 failed, 382 passed in 60.00s\n",
        {"failed": 1, "passed": 382},
    ),
    (
        ["npm", "test"],
        " Test Files  14 passed (14)\n      Tests  170 passed (170)\n",
        {"passed": 170},
    ),
    (
        ["npm", "test"],
        "      Tests  168 passed | 2 skipped (170)\n",
        {"passed": 168, "skipped": 2},
    ),
    (
        # Auto-detection is deliberately *not* smart enough to see Playwright
        # through `npm run test:e2e`. Pinned as a failing expectation so nobody
        # "fixes" the detector by pattern-matching a script name, and so the
        # reason `--format playwright` exists is recorded rather than remembered.
        ["npm", "run", "test:e2e"],
        "  5 passed (18.4s)\n",
        {},
    ),
]

#: (command, output, format, expected counts) — the same output read through the
#: explicit flag, which is what the Makefile and CI actually use.
FORMAT_SELF_TESTS: list[tuple[list[str], str, str, dict[str, int]]] = [
    (["npm", "run", "test:e2e"], "  5 passed (18.4s)\n", "playwright", {"passed": 5}),
    (["npm", "run", "test:e2e"], "  0 passed\n", "playwright", {"passed": 0}),
    (["npm", "run", "test:e2e"], "  4 passed (1 failed)\n", "playwright", {"passed": 4}),
    (["npm", "test"], "      Tests  170 passed (170)\n", "vitest", {"passed": 170}),
]

VERDICT_TESTS: list[tuple[str, dict[str, int], dict[str, object], bool]] = [
    ("healthy tier", {"passed": 11}, {"min_passed": 9, "no_skips": True}, True),
    ("everything skipped", {"passed": 0, "skipped": 9}, {"min_passed": 9, "no_skips": True}, False),
    ("one skip in a no-skip tier", {"passed": 10, "skipped": 1}, {"min_passed": 9, "no_skips": True}, False),
    ("too few ran", {"passed": 2}, {"min_passed": 9, "no_skips": True}, False),
    ("nothing selected", {}, {"min_passed": 9, "no_skips": True}, False),
    ("skips tolerated when allowed", {"passed": 10, "skipped": 4}, {"min_passed": 9, "no_skips": False}, True),
    ("a failure fails the tier", {"passed": 5, "failed": 1}, {"min_passed": 1, "no_skips": False}, False),
    ("an error fails the tier", {"passed": 5, "error": 2}, {"min_passed": 1, "no_skips": False}, False),
]


def self_test() -> int:
    failures = 0
    for command, text, expected in SELF_TESTS:
        actual = parse(command, text)
        for key, value in expected.items():
            if actual.get(key) != value:
                failures += 1
                print(f"SELF-TEST FAIL parse {command}: {key} expected {value}, got {actual}",
                      file=sys.stderr)
        if expected == {} and actual:
            failures += 1
            print(f"SELF-TEST FAIL parse {command}: auto-detection was expected to find "
                  f"nothing here, got {actual}", file=sys.stderr)
    for command, text, fmt, expected in FORMAT_SELF_TESTS:
        actual = parse(command, text, fmt)
        if actual != expected:
            failures += 1
            print(f"SELF-TEST FAIL parse --format {fmt} {command}: expected {expected}, got {actual}",
                  file=sys.stderr)
    for label, counts, requirements, expected_ok in VERDICT_TESTS:
        ok, _ = verdict(counts, requirements["min_passed"], bool(requirements["no_skips"]), "t")
        if ok != expected_ok:
            failures += 1
            print(f"SELF-TEST FAIL verdict [{label}]: expected ok={expected_ok}, got {ok}",
                  file=sys.stderr)
    return failures


def verdict(counts: dict[str, int], min_passed: int, no_skips: bool, name: str) -> tuple[bool, str]:
    """Decide whether a tier may be called green, and say why if it may not."""
    if counts.get("failed") or counts.get("error"):
        return False, f"{name}: tests failed ({counts})"
    passed = counts.get("passed", 0)
    skipped = counts.get("skipped", 0)
    if not counts:
        return False, (
            f"{name}: no summary was parsed at all — the tier produced no counts, "
            "which is what a lost marker or a crashed runner looks like")
    if passed < min_passed:
        return False, f"{name}: only {passed} test(s) passed, this tier requires at least {min_passed}"
    if no_skips and skipped:
        return False, (
            f"{name}: {skipped} test(s) skipped. A tier that skips has not tested the "
            "thing it exists to test — start its service, or run the fast tier instead")
    return True, f"{name}: {passed} passed, {skipped} skipped"


def main() -> int:
    if failures := self_test():
        print(f"run_tier: {failures} self-test case(s) failed, refusing to run", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="tier", help="what to call this tier in the log")
    parser.add_argument("--min-passed", type=int, default=1,
                        help="fewest tests that must pass for this run to count")
    parser.add_argument("--allow-skips", action="store_true",
                        help="tolerate skips (for tiers where the service is genuinely optional)")
    parser.add_argument("--format", choices=("auto", "pytest", "vitest", "playwright"),
                        default="auto", help="how to read the summary (default: from the command)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="the test command, after --")
    args = parser.parse_args()

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        print("error: nothing to run (pass the command after --)", file=sys.stderr)
        return 2

    try:
        # check=False is deliberate: the exit code is part of the verdict below,
        # so an exception here would replace "this tier failed" with a traceback.
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        # A mistyped target must read as "this tier did not run", not as a stack
        # trace that looks like a failure inside the suite.
        print(f"FAIL {args.name}: could not run {' '.join(command)}: {exc}", file=sys.stderr)
        return 1
    output = proc.stdout + proc.stderr
    # Echo the real output first, then the verdict: a gate that hides the suite's
    # own reporting makes a red run impossible to diagnose.
    sys.stdout.write(output)
    sys.stdout.flush()

    counts = parse(command, output, args.format)
    ok, reason = verdict(counts, args.min_passed, not args.allow_skips, args.name)
    if proc.returncode != 0:
        print(f"FAIL {args.name}: the command exited {proc.returncode} ({counts})", file=sys.stderr)
        return proc.returncode
    if not ok:
        print(f"FAIL {reason}", file=sys.stderr)
        return 1
    print(f"OK  {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
