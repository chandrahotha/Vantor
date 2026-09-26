# Strategic Sourcing Optimization Engine

**Product ID:** 06  
**Code:** STRATEGICSOURCE  
**Mission:** Turn procurement requirements, supplier quotes, capacity, risk and policy constraints into explainable, reproducible sourcing allocations.

## Core inputs
RFQLens RFQ/quotes, CostPilot should-cost/benchmarks, SupplierRadar risk/performance, supplier capacity, MOQ/lot constraints, geographic or diversification policies.

## Core outputs
Feasible sourcing scenarios, allocation by supplier/item/period, total landed cost, policy violations, sensitivity analysis, explainable decision package.

## Deterministic core
Constraint-based mixed/integer optimization with deterministic pre-checks and post-solution validation; OR-Tools acceptable.

## Portfolio integration
Consumes Product 02 RFQLens, Product 03 CostPilot and Product 05 SupplierRadar through contracts. Publishes scenario and solution events to Product 01 ProcurementOS.

## Product state machine
`draft → validating → ready → solving → solved / infeasible / failed → approved → archived`

## Primary screens
- S01 Optimization Portfolio
- S02 Create Optimization
- S03 Requirement Intake
- S04 Supplier Eligibility
- S05 Constraint Builder
- S06 Cost Basis Review
- S07 Risk & Policy Controls
- S08 Scenario Workspace
- S09 Solution Comparison
- S10 Allocation Matrix
- S11 Sensitivity Lab
- S12 Infeasibility Explorer
- S13 Decision Brief
- S14 Approval
- S15 Run History
- S16 Export

## Key risks
infeasible models, double-counted costs, hidden unit mismatches, stale supplier capacity, solver non-determinism, over-aggressive soft-constraint relaxation.

## Build rule
The product must be independently runnable, testable and deployable. Portfolio integrations are optional read/analysis adapters until all approval and material-action gates are satisfied.
