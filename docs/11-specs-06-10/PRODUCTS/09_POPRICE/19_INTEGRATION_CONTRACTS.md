# Integration Contracts — PO Price Intelligence Engine

- ContractGuard: contract/PO commercial terms
- CostPilot: historical price/should-cost context
- ProcurementOS: anomaly mission/task
- Spend Intelligence: clean transaction/peer facts where integrated

## Rules
- Consumer never writes producer-owned records.
- Every request carries tenant context and correlation/request id.
- Snapshot-based analytical calls are preferred over mutable live joins.
- Major schema mismatch fails closed.
- Integration outage yields `INTEGRATION_UNAVAILABLE` and a manual/deterministic fallback where possible.
