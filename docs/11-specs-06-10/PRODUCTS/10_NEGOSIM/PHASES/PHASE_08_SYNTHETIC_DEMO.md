# Phase 8 — Synthetic Demo

Product: **AI Supplier Negotiation Simulator** (10)

## Objective
Synthetic negotiation cases across categories and supplier behaviors.

## Required implementation
- Preserve the shared Top-5 API envelope, tenancy, evidence, audit, AI and UI conventions.
- Keep deterministic domain logic independent from AI orchestration.
- Add migrations, tests, audit events and documentation in the same phase as the feature.
- Update `docs/BUILD_LOG.md` after meaningful milestones.
- Record deviations in an ADR before implementation.

## Exit gate
- synthetic dataset is deterministic.
- clean path, edge path and failure/security path are demonstrable.
- demo reset is documented.
- no real credentials or external side effects are possible.
