# Phase 3 — Deterministic Engine

Product: **Strategic Sourcing Optimization Engine** (06)

## Objective
Supplier eligibility, objective functions, hard/soft constraints, feasibility and relaxation logic.

## Required implementation
- Preserve the shared Top-5 API envelope, tenancy, evidence, audit, AI and UI conventions.
- Keep deterministic domain logic independent from AI orchestration.
- Add migrations, tests, audit events and documentation in the same phase as the feature.
- Update `docs/BUILD_LOG.md` after meaningful milestones.
- Record deviations in an ADR before implementation.

## Exit gate
- deterministic engine has golden vectors.
- monetary arithmetic is exact.
- normalized UOM/currency inputs record provenance.
- run inputs, policy versions and output hashes enable replay.
