# Phase 1 — Foundation Domain

Product: **AI Supplier Negotiation Simulator** (10)

## Objective
Simulation/session/round/offer/concession domain with strict tenancy and audit.

## Required implementation
- Preserve the shared Top-5 API envelope, tenancy, evidence, audit, AI and UI conventions.
- Keep deterministic domain logic independent from AI orchestration.
- Add migrations, tests, audit events and documentation in the same phase as the feature.
- Update `docs/BUILD_LOG.md` after meaningful milestones.
- Record deviations in an ADR before implementation.

## Exit gate
- Core entities migrate cleanly.
- tenant_id is present on tenant-scoped records.
- RBAC plus object authorization are tested.
- audit chain is verifiable.
- cross-tenant reads/writes fail safely.
- AI has no direct domain-table write path.
