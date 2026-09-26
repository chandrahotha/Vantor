# Data Model — AI Supplier Negotiation Simulator

## Canonical entities
Simulation, EvidencePack, BuyerObjective, BuyerConstraint, SupplierPersona, NegotiationRound, Offer, Concession, Response, Branch, PressureTest, SimulationScore, Debrief, PreparationBrief, AIJob, ExportJob, AuditEvent

## Key fields / facts
opening position, target, walk-away, concessions, cost/risk facts, supplier priorities, scenario assumptions, persona parameters, round state, offer history, score dimensions

## Cross-cutting requirements
- All tenant-owned entities include `tenant_id`.
- Use UUID identifiers.
- Money = integer minor units or Decimal + ISO 4217.
- Quantity = value + UOM + normalized value + conversion provenance/version.
- Every material analytical result stores input snapshot/hash and rules/policy version.
- Evidence records reference immutable document/version and location where applicable.
- Audit records capture actor, action, before/after hashes, request/correlation id and reason where necessary.
- Unique constraints include tenant scope.
- Effective-dated records prevent overlapping active policies where domain rules require it.
