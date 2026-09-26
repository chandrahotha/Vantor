# PO Price Intelligence Engine

**Product ID:** 09  
**Code:** POPRICE  
**Mission:** Compare PO pricing against clean historical baselines, peer purchases, contract terms and cost/market context to identify explainable commercial anomalies.

## Core inputs
PO lines, supplier/item master, UOM/currency, contract prices, price history, freight/discount/tax/incoterm context, category benchmarks.

## Core outputs
Comparable price baseline, anomaly state, variance decomposition, leakage amount, evidence, workflow case and optional negotiation/sourcing handoff.

## Deterministic core
Deterministic comparability, normalized price basis, baseline statistics and threshold rules; optional AI explanation only.

## Portfolio integration
Consumes ContractGuard contract/PO facts and CostPilot history/baselines. Feeds anomalies to ProcurementOS missions and CostPilot negotiation preparation.

## Product state machine
`new → normalizing → comparable → analyzed → exception / clear → accepted / dismissed → closed`

## Primary screens
- P01 Price Control Tower
- P02 PO Intake
- P03 PO Line Detail
- P04 Comparability Review
- P05 Price History
- P06 Benchmark Builder
- P07 Anomaly Analysis
- P08 Leakage Breakdown
- P09 Contract Check
- P10 Review Queue
- P11 Investigation Workspace
- P12 Resolution
- P13 Reports
- P14 Export
- P15 Rules & Thresholds
- P16 Run History

## Key risks
incomparable prices presented as equivalent, stale history, contract basis mismatches, false positives, unit/currency mistakes.

## Build rule
The product must be independently runnable, testable and deployable. Portfolio integrations are optional read/analysis adapters until all approval and material-action gates are satisfied.
