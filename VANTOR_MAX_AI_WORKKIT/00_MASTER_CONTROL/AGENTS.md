# AGENTS.md — VANTOR Coding Agent Contract

## Working mode

Operate as an evidence-driven engineering agent. Inspect first. Edit only after establishing the invariant and dependencies. Do not make broad style or architecture changes unrelated to the current phase.

## Code safety

- Preserve tenant isolation.
- Never bypass approval/SoD rules to make tests pass.
- Never trust client totals/currency/status.
- Never execute external network effects before durable commit.
- Never log secrets or document contents.

## Verification

For a changed backend invariant, run the relevant unit tests and PostgreSQL integration/concurrency tests. For changed UI, run typecheck/lint/component tests and browser E2E/visual/a11y for affected screens.

## Completion report

Each completed task must report: files changed, why, tests, observed output, migration impact, deployment impact, and known limitations.
