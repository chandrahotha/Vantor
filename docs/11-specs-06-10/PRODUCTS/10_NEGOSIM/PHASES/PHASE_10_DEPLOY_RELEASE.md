# Phase 10 — Deploy & Release

Product: **AI Supplier Negotiation Simulator** (10)

## Objective
Deployment, cost controls, observability, model fallback, sandbox guarantees and release gate.

## Required implementation
- Preserve the shared Top-5 API envelope, tenancy, evidence, audit, AI and UI conventions.
- Keep deterministic domain logic independent from AI orchestration.
- Add migrations, tests, audit events and documentation in the same phase as the feature.
- Update `docs/BUILD_LOG.md` after meaningful milestones.
- Record deviations in an ADR before implementation.

## Exit gate
- deployment from clean environment is reproducible.
- observability is configured.
- backup/restore and migration runbooks exist.
- integration contract is versioned.
- public demo mode is safe.
- release checklist is complete.
