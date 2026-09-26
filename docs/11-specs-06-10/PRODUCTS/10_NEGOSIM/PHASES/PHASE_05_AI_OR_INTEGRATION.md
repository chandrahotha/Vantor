# Phase 5 — AI / Integration

Product: **AI Supplier Negotiation Simulator** (10)

## Objective
Ai orchestration for simulation turns, injection defenses and output validation.

## Required implementation
- Preserve the shared Top-5 API envelope, tenancy, evidence, audit, AI and UI conventions.
- Keep deterministic domain logic independent from AI orchestration.
- Add migrations, tests, audit events and documentation in the same phase as the feature.
- Update `docs/BUILD_LOG.md` after meaningful milestones.
- Record deviations in an ADR before implementation.

## Exit gate
- AI/integration calls use typed contracts.
- external content is treated as untrusted data.
- AI results are schema/evidence validated.
- outages fall back to deterministic/manual workflows.
