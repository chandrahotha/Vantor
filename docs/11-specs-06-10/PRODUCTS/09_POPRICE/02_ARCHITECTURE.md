# Architecture — PO Price Intelligence Engine

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

Mission: Compare PO pricing against clean historical baselines, peer purchases, contract terms and cost/market context to identify explainable commercial anomalies.

Inputs: PO lines, supplier/item master, UOM/currency, contract prices, price history, freight/discount/tax/incoterm context, category benchmarks.

Outputs: Comparable price baseline, anomaly state, variance decomposition, leakage amount, evidence, workflow case and optional negotiation/sourcing handoff.

## Reliability

Use transaction boundaries around state transitions. Use outbox/event records for cross-product events. Never publish an event before the related database transaction is durable.

## Read model

Analytical dashboards may use read-optimized projections, but canonical domain data remains in the authoritative relational model.
