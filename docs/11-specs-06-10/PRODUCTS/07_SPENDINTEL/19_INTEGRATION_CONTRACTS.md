# Integration Contracts — Procurement Spend Intelligence Agent

- CostPilot: clean price history and spend baselines
- RFQLens: supplier/category history and market context
- SupplierRadar: supplier spend concentration/exposure
- ProcurementOS: opportunity missions

## Rules
- Consumer never writes producer-owned records.
- Every request carries tenant context and correlation/request id.
- Snapshot-based analytical calls are preferred over mutable live joins.
- Major schema mismatch fails closed.
- Integration outage yields `INTEGRATION_UNAVAILABLE` and a manual/deterministic fallback where possible.
