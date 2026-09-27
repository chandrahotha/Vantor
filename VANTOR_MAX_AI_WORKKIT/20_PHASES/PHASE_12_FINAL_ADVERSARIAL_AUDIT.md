# Phase 12 — FINAL ADVERSARIAL AUDIT

## Objective

Re-scan full repo for old patterns, run complete CI, compare docs to code.

## Required behavior

- Inspect the current code before editing.
- Identify all callers and tests of any function/endpoint being changed.
- Make the smallest coherent change that establishes one canonical rule.
- Add or update regression tests before declaring completion.
- Run targeted tests, then the wider suite.
- Update implementation map and changelog.

## Exit criteria

Zero open Critical/High and every 10/10 gate green.

## Do not do

- Do not invent missing business requirements.
- Do not silently remove functionality.
- Do not leave duplicate competing implementations of the same rule.
- Do not mark a phase complete merely because code compiles.
