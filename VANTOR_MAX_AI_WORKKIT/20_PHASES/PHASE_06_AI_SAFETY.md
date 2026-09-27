<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Phase 06 — AI SAFETY

## Objective

Evidence contract, immutable prompt policy, tool permissions, evaluation suite and provider governance.

## Required behavior

- Inspect the current code before editing.
- Identify all callers and tests of any function/endpoint being changed.
- Make the smallest coherent change that establishes one canonical rule.
- Add or update regression tests before declaring completion.
- Run targeted tests, then the wider suite.
- Update implementation map and changelog.

## Exit criteria

Adversarial AI eval thresholds pass.

## Do not do

- Do not invent missing business requirements.
- Do not silently remove functionality.
- Do not leave duplicate competing implementations of the same rule.
- Do not mark a phase complete merely because code compiles.
