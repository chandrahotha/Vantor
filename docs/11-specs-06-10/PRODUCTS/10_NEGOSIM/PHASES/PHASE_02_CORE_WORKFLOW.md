# Phase 2 — Core Workflow

Product: **AI Supplier Negotiation Simulator** (10)

## Objective
Deterministic offer ledger, objective/constraint model and concession calculations.

## Required implementation
- Preserve the shared Top-5 API envelope, tenancy, evidence, audit, AI and UI conventions.
- Keep deterministic domain logic independent from AI orchestration.
- Add migrations, tests, audit events and documentation in the same phase as the feature.
- Update `docs/BUILD_LOG.md` after meaningful milestones.
- Record deviations in an ADR before implementation.

## Exit gate
- state machine is explicit and server-enforced.
- every transition has actor, authorization and audit event.
- idempotent commands are defined.
- stale/race/concurrency paths are tested.
