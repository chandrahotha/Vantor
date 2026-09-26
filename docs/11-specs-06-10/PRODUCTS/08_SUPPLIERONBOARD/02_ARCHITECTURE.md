# Architecture — Supplier Onboarding & Qualification Agent

## Layers

`Web → API → Application Services → Domain Services → Deterministic Engine → Persistence`

AI is parallel to application services and may only access explicitly typed tools.

## Suggested service areas

- `auth/`
- `tenancy/`
- `audit/`
- `documents/` where applicable
- `integration/`
- `domain/`
- `engine/`
- `ai/`
- `approvals/`
- `exports/`
- `worker/`
- `web/`

## Product-specific core

Mission: Turn supplier submissions into structured qualification cases with evidence-backed checks, missing-document detection, risk signals and approval workflows.

Inputs: Supplier registration forms, certifications, tax documents, bank details, insurance, ESG questionnaires, quality certificates, policies and supporting documents.

Outputs: Supplier profile, evidence map, completeness status, qualification scorecard, compliance gaps, approval routing and onboarding decision package.

## Reliability

Use transaction boundaries around state transitions. Use outbox/event records for cross-product events. Never publish an event before the related database transaction is durable.

## Read model

Analytical dashboards may use read-optimized projections, but canonical domain data remains in the authoritative relational model.
