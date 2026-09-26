# Architecture — Procurement Spend Intelligence Agent

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

Mission: Convert raw purchasing transactions into trustworthy spend visibility, category intelligence, supplier concentration, maverick spend and savings opportunities.

Inputs: POs, invoices, supplier master, item/category hierarchy, GL/account mappings, contracts, historical prices and organizational dimensions.

Outputs: Normalized spend cube, classification confidence, leakage findings, maverick spend cases, savings opportunities, concentration metrics and executive reports.

## Reliability

Use transaction boundaries around state transitions. Use outbox/event records for cross-product events. Never publish an event before the related database transaction is durable.

## Read model

Analytical dashboards may use read-optimized projections, but canonical domain data remains in the authoritative relational model.
