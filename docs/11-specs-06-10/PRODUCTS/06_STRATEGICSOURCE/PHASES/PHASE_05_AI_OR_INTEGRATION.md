# Phase 5 — AI / Integration

Product: **Strategic Sourcing Optimization Engine** (06)

## Objective
Integration adapters to rfqlens/costpilot/supplierradar plus evidence and provenance.

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
