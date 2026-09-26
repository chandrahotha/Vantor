# Integration Contracts — Strategic Sourcing Optimization Engine

- RFQLens: sourcing event, quotes, normalized commercial basis
- CostPilot: should-cost and benchmark snapshots
- SupplierRadar: risk/performance snapshot
- ProcurementOS: approved decision brief / mission task

## Rules
- Consumer never writes producer-owned records.
- Every request carries tenant context and correlation/request id.
- Snapshot-based analytical calls are preferred over mutable live joins.
- Major schema mismatch fails closed.
- Integration outage yields `INTEGRATION_UNAVAILABLE` and a manual/deterministic fallback where possible.
