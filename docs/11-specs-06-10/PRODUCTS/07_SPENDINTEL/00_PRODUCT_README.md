# Procurement Spend Intelligence Agent

**Product ID:** 07  
**Code:** SPENDINTEL  
**Mission:** Convert raw purchasing transactions into trustworthy spend visibility, category intelligence, supplier concentration, maverick spend and savings opportunities.

## Core inputs
POs, invoices, supplier master, item/category hierarchy, GL/account mappings, contracts, historical prices and organizational dimensions.

## Core outputs
Normalized spend cube, classification confidence, leakage findings, maverick spend cases, savings opportunities, concentration metrics and executive reports.

## Deterministic core
Deterministic spend aggregation, matching and rules; AI-assisted classification/entity resolution with human review and confidence thresholds.

## Portfolio integration
Feeds classified spend, price baselines and opportunity records to CostPilot, RFQLens and SupplierRadar; can create missions for ProcurementOS.

## Product state machine
`uploaded → profiling → classifying → reviewing → published → superseded`

## Primary screens
- P01 Spend Command Center
- P02 Data Intake
- P03 Data Quality
- P04 Spend Cube
- P05 Category Explorer
- P06 Supplier Concentration
- P07 Maverick Spend
- P08 Savings Opportunities
- P09 Price Leakage
- P10 Classification Review
- P11 Entity Resolution
- P12 What-if Scenario
- P13 Executive Brief
- P14 Rules & Taxonomy
- P15 AI Run History
- P16 Export

## Key risks
classification drift, double-counted transactions, unit/currency errors, taxonomy changes, false savings claims, duplicate suppliers.

## Build rule
The product must be independently runnable, testable and deployable. Portfolio integrations are optional read/analysis adapters until all approval and material-action gates are satisfied.
