# Architecture — Strategic Sourcing Optimization Engine

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

Mission: Turn procurement requirements, supplier quotes, capacity, risk and policy constraints into explainable, reproducible sourcing allocations.

Inputs: RFQLens RFQ/quotes, CostPilot should-cost/benchmarks, SupplierRadar risk/performance, supplier capacity, MOQ/lot constraints, geographic or diversification policies.

Outputs: Feasible sourcing scenarios, allocation by supplier/item/period, total landed cost, policy violations, sensitivity analysis, explainable decision package.

## Reliability

Use transaction boundaries around state transitions. Use outbox/event records for cross-product events. Never publish an event before the related database transaction is durable.

## Read model

Analytical dashboards may use read-optimized projections, but canonical domain data remains in the authoritative relational model.
