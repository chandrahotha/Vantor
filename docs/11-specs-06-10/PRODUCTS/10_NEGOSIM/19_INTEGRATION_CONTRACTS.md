# Integration Contracts — AI Supplier Negotiation Simulator

- RFQLens: quote/commercial snapshot
- CostPilot: should-cost and target position
- SupplierRadar: risk/performance context
- ProcurementOS: optional draft preparation brief only

## Rules
- Consumer never writes producer-owned records.
- Every request carries tenant context and correlation/request id.
- Snapshot-based analytical calls are preferred over mutable live joins.
- Major schema mismatch fails closed.
- Integration outage yields `INTEGRATION_UNAVAILABLE` and a manual/deterministic fallback where possible.
