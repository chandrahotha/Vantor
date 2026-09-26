# Data Model — Procurement Spend Intelligence Agent

## Canonical entities
SpendBatch, SpendTransaction, SupplierEntity, ItemEntity, CategoryNode, OrgNode, GLAccount, TaxonomyVersion, ClassificationResult, MatchCandidate, DataQualityIssue, SpendCubeSnapshot, ConcentrationMetric, MaverickFinding, LeakageFinding, SavingsOpportunity, ReviewTask, RulePack, AIJob, ExportJob, AuditEvent

## Key fields / facts
transaction amount, quantity, currency, UOM, invoice/PO identifiers, supplier canonical id, item canonical id, category path, cost center, GL account, business unit, location, contract reference, source-system metadata

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
