# Top-10 Contract Compatibility Matrix

| Producer | Consumer | Contract payload | Direction | Direct DB access |
|---|---|---|---|---|
| RFQLens (#2) | Strategic Sourcing (#6) | RFQ lines, normalized quotes, eligibility inputs | read | NO |
| CostPilot (#3) | Strategic Sourcing (#6) | should-cost, benchmark, cost-basis snapshot | read | NO |
| SupplierRadar (#5) | Strategic Sourcing (#6) | risk/performance/capacity snapshot | read | NO |
| Spend Intelligence (#7) | RFQLens (#2) | category/supplier/spend context | read | NO |
| Spend Intelligence (#7) | CostPilot (#3) | price/spend history | read | NO |
| Spend Intelligence (#7) | SupplierRadar (#5) | exposure/concentration | read | NO |
| Supplier Onboarding (#8) | SupplierRadar (#5) | qualification state/evidence refs | event/read | NO |
| Supplier Onboarding (#8) | ProcurementOS (#1) | onboarding mission/tasks | event/read | NO |
| ContractGuard (#4) | PO Price (#9) | PO/contract price references | read | NO |
| CostPilot (#3) | PO Price (#9) | price baseline/should-cost context | read | NO |
| PO Price (#9) | ProcurementOS (#1) | anomaly case/task | event/read | NO |
| PO Price (#9) | CostPilot (#3) | validated price observations | event/read | NO |
| RFQLens (#2) | Negotiation Simulator (#10) | quote/commercial snapshot | read-only | NO |
| CostPilot (#3) | Negotiation Simulator (#10) | cost position/target | read-only | NO |
| SupplierRadar (#5) | Negotiation Simulator (#10) | risk/performance context | read-only | NO |

## Critical rule
Consumers store the producer's snapshot identifier and hash, not a mutable copy that loses provenance. Reconciliation can be repeated using the producer contract version.
