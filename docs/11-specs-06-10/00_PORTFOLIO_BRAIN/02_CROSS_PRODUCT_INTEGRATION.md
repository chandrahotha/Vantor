# Cross-Product Integration Contract

## Product graph

`RFQLens → Strategic Sourcing → ProcurementOS`

`RFQLens → CostPilot → Strategic Sourcing`

`SupplierRadar → Strategic Sourcing`

`Spend Intelligence → RFQLens / CostPilot / SupplierRadar`

`Supplier Onboarding → SupplierRadar / ProcurementOS / ContractGuard`

`PO Price Intelligence → CostPilot / ContractGuard / ProcurementOS`

`Negotiation Simulator ← RFQLens + CostPilot + SupplierRadar (read-only scenario inputs)`

## Allowed integration pattern

Use versioned REST/event contracts. Preferred events:

- `sourcing.scenario.created`
- `sourcing.scenario.solved`
- `spend.category.detected`
- `spend.opportunity.created`
- `supplier.onboarding.completed`
- `supplier.qualification.changed`
- `po.price.anomaly.detected`
- `negotiation.simulation.completed`

## Prohibited patterns

- shared database writes
- cross-repository imports
- direct access to another product's internal ORM models
- AI-to-AI uncontrolled delegation
- automatic supplier award or commitment from an integration event

## Contract versioning

Each product publishes an `integration/contract.json` with:
- product name and version
- schema version
- event names
- resource identifiers
- semantic definitions
- idempotency rules
- tenant-scoped authorization requirements
- source/evidence expectations

Consumers must reject unknown major versions and tolerate additive minor-version fields.

## Portfolio-level decision chain

`ingest → validate → deterministic analysis → scenario/exception/result → policy evaluation → AI explanation/draft (optional) → human approval if material → audit → export/event`
