# Integration Contracts — Supplier Onboarding & Qualification Agent

- SupplierRadar: qualification/risk status and evidence references
- ProcurementOS: onboarding tasks/missions
- ContractGuard: controlled policy references where contract compliance applies

## Rules
- Consumer never writes producer-owned records.
- Every request carries tenant context and correlation/request id.
- Snapshot-based analytical calls are preferred over mutable live joins.
- Major schema mismatch fails closed.
- Integration outage yields `INTEGRATION_UNAVAILABLE` and a manual/deterministic fallback where possible.
