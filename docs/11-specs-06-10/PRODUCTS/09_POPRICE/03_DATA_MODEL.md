# Data Model — PO Price Intelligence Engine

## Canonical entities
PORecord, POLine, PriceObservation, PriceBasis, ComparabilityAssessment, PeerGroup, BaselineModel, ThresholdRule, PriceAnomaly, LeakageComponent, ContractPriceReference, ReviewCase, ResolutionAction, PriceRun, ExportJob, AuditEvent

## Key fields / facts
unit price, extended price, currency, UOM, quantity basis, freight, discount, tax mode, Incoterm, lead time, contract reference, date, supplier, item, plant/site, comparable set id

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
