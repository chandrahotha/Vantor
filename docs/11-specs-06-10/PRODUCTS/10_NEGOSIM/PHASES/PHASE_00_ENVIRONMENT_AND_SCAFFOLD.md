# Phase 0 — Environment & Scaffold

Product: **AI Supplier Negotiation Simulator** (10)

## Objective
Environment, isolated simulator runtime and version capture.

## Required implementation
- Preserve the shared Top-5 API envelope, tenancy, evidence, audit, AI and UI conventions.
- Keep deterministic domain logic independent from AI orchestration.
- Add migrations, tests, audit events and documentation in the same phase as the feature.
- Update `docs/BUILD_LOG.md` after meaningful milestones.
- Record deviations in an ADR before implementation.

## Exit gate
- Clean environment bootstrap works.
- Exact runtime/tool versions are captured in the repository.
- `/healthz` and `/api/v1/health` return the standard envelope.
- CI scaffold runs lint, typecheck, unit, integration, security, dependency and secret checks.
