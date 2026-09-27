# Phase 09 — SCREEN REBUILD

## Objective

Rebuild all operational screens and add first-class Approval/Invoice/Health/Admin surfaces.

## Required behavior

- Inspect the current code before editing.
- Identify all callers and tests of any function/endpoint being changed.
- Make the smallest coherent change that establishes one canonical rule.
- Add or update regression tests before declaring completion.
- Run targeted tests, then the wider suite.
- Update implementation map and changelog.

## Exit criteria

All golden journeys are possible through UI without hidden SQL/manual steps.

## Do not do

- Do not invent missing business requirements.
- Do not silently remove functionality.
- Do not leave duplicate competing implementations of the same rule.
- Do not mark a phase complete merely because code compiles.
