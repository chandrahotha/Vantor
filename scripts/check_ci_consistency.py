#!/usr/bin/env python3
"""Structural checks on the CI workflow, so a gate cannot be quietly disarmed.

The repository's own rule is that CI must be able to fail ("a green badge must
mean the suite actually ran", docs/01-product/requirements.md §4). Two things
keep breaking that rule, and neither is visible from a passing run:

* **A step whose condition is duplicated but not identical.** The heavy-tier
  predicate appears once per heavy job/step *and* in the `concurrency:` group
  that decides whether a run may be cancelled. Editing one copy is enough to
  re-open the hole — for a while the weekly full-suite run shared a concurrency
  group with pushes to main, so any push could cancel the only run that proves
  row-level security, and a cancelled run leaves no red badge to notice.
* **A step that cannot fail.** `continue-on-error`, `|| true` and an exit-code
  swallowed into a log line all turn a real check into decoration. The
  `policy` job was the same idea in a different costume: it compared the trigger
  event against the workflow's own `on:` list, which no run can violate.

`--check` is offline and cheap, so it runs on every push.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = [ROOT / ".github" / "workflows" / "ci.yml", ROOT / ".github" / "workflows" / "release.yml"]

#: One copy of the heavy-tier predicate is written in full; anything shorter is
#: a job that stopped meaning "the tier that needs services".
MIN_HEAVY_PREDICATE_LINES = 1

#: Neutralising patterns that make a check unable to fail. `|| true` and
#: `continue-on-error` are the classic forms; `--exit-zero` is pip-audit's way of
#: reporting vulnerabilities while still exiting 0.
NEUTRALISE_RE = re.compile(
    r"continue-on-error:\s*true"
    r"|\|\|\s*true\b"
    r"|--exit-zero\b"
    r"|\|\|\s*echo\b"
    r"|\btrap\s+'exit 0'"
)

#: `github.event_name == 'x'` or `github.event.inputs.full_suite == 'true'`.
#: Captured as a set so that reordering the two halves of an `||` is not
#: mistaken for drift, while dropping or adding a condition is.
ATOM_RE = re.compile(r"(github\.[A-Za-z_.]+)\s*(===?|!=)\s*'([^']*)'")


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def heavy_predicates(text: str) -> list[tuple[int, str]]:
    """Every `if:` line that mentions `full_suite`, as (line number, text)."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("if:") and "full_suite" in stripped:
            found.append((number, stripped))
    return found


def atoms(expression: str) -> frozenset[tuple[str, str, str]]:
    return frozenset(
        (m.group(1), m.group(2), m.group(3)) for m in ATOM_RE.finditer(expression)
    )


def job_names(text: str) -> set[str]:
    """Top-level job names: two-space keys under `jobs:`."""
    return {
        m.group(1)
        for m in re.finditer(r"^  ([a-z][a-z0-9-]*):\s*$", text, re.MULTILINE)
    }


def needsReferences(text: str) -> list[tuple[int, str]]:
    out = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("needs:"):
            value = stripped.split("needs:", 1)[1].strip()
            names = re.findall(r"[a-z][a-z0-9-]*", value)
            for name in names:
                out.append((number, name))
    return out


def check_heavy_predicate_is_one_predicate(text: str, where: str) -> list[str]:
    problems: list[str] = []
    predicates = heavy_predicates(text)
    if len(predicates) < MIN_HEAVY_PREDICATE_LINES:
        return problems
    reference = atoms(predicates[0][1])
    for number, line in predicates[1:]:
        if atoms(line) != reference:
            problems.append(
                f"{where} line {number}: the heavy-tier condition is not the same "
                f"predicate as line {predicates[0][0]}\n"
                f"    {sorted(a[2] for a in atoms(line))} vs "
                f"{sorted(a[2] for a in reference)}\n"
                "    These decide whether the services-backed tiers run; a copy "
                "that drifted means one tier runs on events the others do not.")
    return problems


def check_concurrency_matches_heavy_predicate(text: str, where: str) -> list[str]:
    """The run-cancellation group must key on the same predicate as the tiers.

    Otherwise a run can be cancelled by an event that is *not* the one that made
    it heavy, which is how the weekly full-suite run used to share a group with
    ordinary pushes to main.
    """
    problems: list[str] = []
    group = re.search(r"^concurrency:\s*\n((?:[ \t]+\S.*\n)+)", text, re.MULTILINE)
    if not group:
        return problems
    block = group.group(1)
    group_line = next((l for l in block.splitlines() if l.strip().startswith("group:")), "")
    cancel_line = next((l for l in block.splitlines() if "cancel-in-progress" in l), "")
    predicates = heavy_predicates(text)
    if not predicates or not group_line:
        return problems
    reference = atoms(predicates[0][1])
    if atoms(group_line) != reference:
        problems.append(
            f"{where}: the `concurrency.group` does not test the same condition as "
            f"the heavy tiers ({sorted(a[2] for a in reference)}).\n"
            f"    group tests {sorted(a[2] for a in atoms(group_line))}\n"
            "    A heavy run that shares a cancellation group with a push can be "
            "killed mid-flight, and a cancelled run reports no failure at all.")
    if re.search(r"cancel-in-progress:\s*true\s*$", cancel_line.strip()):
        problems.append(
            f"{where}: `cancel-in-progress: true` is unconditional, so it also "
            "applies to the weekly full-suite run. Key it on the same predicate.")
    return problems


def check_neutralised_steps(text: str, where: str) -> list[str]:
    problems = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("#"):
            continue  # a comment describing the pattern is not the pattern
        if NEUTRALISE_RE.search(line):
            problems.append(
                f"{where} line {number}: this makes a check unable to fail: "
                f"`{line.strip()[:100]}`")
    return problems


def check_needs_resolve(text: str, where: str) -> list[str]:
    jobs = job_names(text)
    problems = []
    for number, name in needsReferences(text):
        if name not in jobs:
            problems.append(
                f"{where} line {number}: needs `{name}`, which is not a job in this "
                f"workflow (jobs: {', '.join(sorted(jobs)) or 'none'})")
    return problems


def check_timeouts(text: str, where: str) -> list[str]:
    """A job with no `timeout-minutes` can hang until the runner's 6-hour limit.

    GitHub's own default is 360 minutes for jobs and 5 for steps, which is long
    enough that a wedged Postgres service container reads as "CI is still
    running" for most of a working day.
    """
    problems = []
    in_jobs = False
    current: str | None = None
    seen: dict[str, bool] = {}
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            continue
        if in_jobs and re.match(r"^[a-z]", line):
            in_jobs = False
        if not in_jobs:
            continue
        job = re.match(r"^  ([a-z][a-z0-9-]*):\s*$", line)
        if job:
            current = job.group(1)
            seen.setdefault(current, False)
            continue
        if current and re.search(r"timeout-minutes\s*:", line):
            seen[current] = True
    for job, has in seen.items():
        if not has:
            problems.append(f"{where}: job `{job}` has no `timeout-minutes`")
    return problems


def check(paths: list[pathlib.Path]) -> int:
    problems: list[str] = []
    checked = 0
    for path in paths:
        if not path.exists():
            problems.append(f"{path.relative_to(ROOT)} is missing")
            continue
        checked += 1
        text = read(path)
        where = path.relative_to(ROOT).as_posix()
        problems.extend(check_heavy_predicate_is_one_predicate(text, where))
        problems.extend(check_concurrency_matches_heavy_predicate(text, where))
        problems.extend(check_neutralised_steps(text, where))
        problems.extend(check_needs_resolve(text, where))
        if path.name == "ci.yml":
            problems.extend(check_timeouts(text, where))

    if problems:
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        print(f"\n{len(problems)} problem(s) across {checked} workflow(s)", file=sys.stderr)
        return 1
    print(f"CI structure OK: {checked} workflow(s), one heavy-tier predicate, "
          "no neutralised checks, every `needs:` resolves, every job has a timeout")
    return 0


# --- self-tests ---------------------------------------------------------------
#
# Every rule above has to be able to fail, and the only proof of that is a case
# that runs it against text that breaks it. A check whose happy path is the only
# path exercised is a check that has not been tested.

HEAVY = (
    "        if: ${{ (github.event_name == 'workflow_dispatch' && "
    "github.event.inputs.full_suite == 'true') || github.event_name == 'schedule' }}\n"
)

SELF_TESTS: list[tuple[str, str, int]] = [
    (
        "identical predicates pass",
        "jobs:\n  a:\n" + HEAVY + "  b:\n" + HEAVY,
        0,
    ),
    (
        "a predicate that dropped the schedule arm is drift",
        "jobs:\n  a:\n" + HEAVY + "  b:\n        if: ${{ github.event.inputs.full_suite == 'true' }}\n",
        1,
    ),
    (
        "reordering the two arms is not drift",
        "jobs:\n  a:\n        if: ${{ github.event_name == 'schedule' || (github.event_name == 'workflow_dispatch' && github.event.inputs.full_suite == 'true') }}\n"
        + "  b:\n" + HEAVY,
        0,
    ),
    (
        "`|| true` is a check that cannot fail",
        "jobs:\n  a:\n        run: pytest -q || true\n",
        1,
    ),
    (
        "`continue-on-error: true` is the same thing in YAML",
        "jobs:\n  a:\n        continue-on-error: true\n",
        1,
    ),
    (
        "a comment about the pattern is not the pattern",
        "jobs:\n  a:\n        # we never use `|| true` here\n        run: pytest -q\n",
        0,
    ),
    (
        "needs pointing at a job that does not exist",
        "jobs:\n  a:\n    needs: [typo]\n",
    1,
    ),
    (
        "needs pointing at a real job",
        "jobs:\n  a:\n    runs-on: x\n  b:\n    needs: [a]\n",
        0,
    ),
]

CONCURRENCY_SELF_TESTS: list[tuple[str, str, int]] = [
    (
        "group keyed on the same predicate as the tiers",
        "concurrency:\n"
        "  group: ${{ github.workflow }}-${{ github.ref }}-${{ (github.event_name == 'schedule' || (github.event_name == 'workflow_dispatch' && github.event.inputs.full_suite == 'true')) && 'full' || 'fast' }}\n"
        "  cancel-in-progress: ${{ github.event_name != 'schedule' && !(github.event_name == 'workflow_dispatch' && github.event.inputs.full_suite == 'true') }}\n"
        "jobs:\n  a:\n" + HEAVY,
        0,
    ),
    (
        "the old shape: a bare ref group shares cancellation with the weekly run",
        "concurrency:\n  group: ${{ github.workflow }}-${{ github.ref }}\n  cancel-in-progress: true\n"
        "jobs:\n  a:\n" + HEAVY,
        2,
    ),
]

TIMEOUT_SELF_TESTS: list[tuple[str, str, int]] = [
    ("a job with a timeout", "jobs:\n  a:\n    runs-on: x\n    timeout-minutes: 20\n", 0),
    ("a job without one", "jobs:\n  a:\n    runs-on: x\n", 1),
    ("two jobs, one missing it", "jobs:\n  a:\n    timeout-minutes: 5\n  b:\n    runs-on: x\n", 1),
    ("a top-level key after jobs ends the scan",
     "jobs:\n  a:\n    runs-on: x\non:\n  push:\n", 1),
    ("a workflow with no jobs at all", "on:\n  push:\n", 0),
]


def self_test() -> int:
    failures = 0
    for label, text, expected in SELF_TESTS:
        found = (
            len(check_heavy_predicate_is_one_predicate(text, "t.yml"))
            + len(check_neutralised_steps(text, "t.yml"))
            + len(check_needs_resolve(text, "t.yml"))
        )
        if found != expected:
            failures += 1
            print(f"SELF-TEST FAIL [{label}]: expected {expected} problem(s), got {found}",
                  file=sys.stderr)
    for label, text, expected in CONCURRENCY_SELF_TESTS:
        found = (
            len(check_concurrency_matches_heavy_predicate(text, "t.yml"))
            + len(check_neutralised_steps(text, "t.yml"))
        )
        if found != expected:
            failures += 1
            print(f"SELF-TEST FAIL [{label}]: expected {expected} problem(s), got {found}",
                  file=sys.stderr)
    for label, text, expected in TIMEOUT_SELF_TESTS:
        found = len(check_timeouts(text, "t.yml"))
        if found != expected:
            failures += 1
            print(f"SELF-TEST FAIL [{label}]: expected {expected} problem(s), got {found}",
                  file=sys.stderr)
    return failures


def main() -> int:
    if failures := self_test():
        print(f"check_ci_consistency: {failures} self-test case(s) failed, refusing to run",
              file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if a gate is disarmed")
    parser.parse_args()
    return check(WORKFLOWS)


if __name__ == "__main__":
    sys.exit(main())
