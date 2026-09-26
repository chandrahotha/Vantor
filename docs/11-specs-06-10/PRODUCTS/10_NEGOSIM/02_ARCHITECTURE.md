# Architecture — AI Supplier Negotiation Simulator

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

Mission: Let procurement professionals rehearse negotiations using structured supplier evidence, cost positions, constraints and simulated counterpart behavior without changing live procurement systems.

Inputs: Approved/synthetic supplier facts, RFQLens quotes, CostPilot cost positions, SupplierRadar risk/performance, negotiation objectives and policy limits.

Outputs: Negotiation rounds, supplier responses, concession ladder effects, buyer scorecards, post-session debrief and evidence-backed preparation brief.

## Reliability

Use transaction boundaries around state transitions. Use outbox/event records for cross-product events. Never publish an event before the related database transaction is durable.

## Read model

Analytical dashboards may use read-optimized projections, but canonical domain data remains in the authoritative relational model.
