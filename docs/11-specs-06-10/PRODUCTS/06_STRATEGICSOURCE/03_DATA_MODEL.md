# Data Model — Strategic Sourcing Optimization Engine

## Canonical entities
SourcingEvent, Requirement, RequirementLine, SupplierOption, SupplierConstraint, CostBasisSnapshot, RiskSnapshot, PolicyPack, ObjectiveFunction, HardConstraint, SoftConstraint, OptimizationRun, OptimizationVariable, OptimizationSolution, Allocation, SolutionMetric, SensitivityRun, InfeasibilityRecord, Approval, DecisionBrief, ExportJob, AuditEvent

## Key fields / facts
supplier eligibility, capacity by period, MOQ/lot, minimum/maximum allocation, single/multi-source rules, lead-time windows, geography, risk caps, category policies, price/cost basis, diversity thresholds

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
