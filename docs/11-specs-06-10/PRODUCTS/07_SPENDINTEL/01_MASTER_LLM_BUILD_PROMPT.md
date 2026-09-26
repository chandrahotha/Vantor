# Master LLM Build Prompt — Procurement Spend Intelligence Agent

Build a complete enterprise procurement application, not a prototype.

## Product mission
Convert raw purchasing transactions into trustworthy spend visibility, category intelligence, supplier concentration, maverick spend and savings opportunities.

## Architecture
Use the inherited Top-5 architecture and the product-specific deterministic engine. Keep `engine/` pure enough to run golden vectors without the web server or LLM. Keep `ai/` behind explicit interfaces. Use typed Pydantic request/response models and versioned schemas.

## Core inputs
POs, invoices, supplier master, item/category hierarchy, GL/account mappings, contracts, historical prices and organizational dimensions.

## Core outputs
Normalized spend cube, classification confidence, leakage findings, maverick spend cases, savings opportunities, concentration metrics and executive reports.

## Required controls
- tenant isolation
- RBAC and object authorization
- segregation of duties
- immutable evidence after finalization
- append-only/hash-chained audit
- idempotent async jobs
- exact money math
- explicit comparability/quality states where relevant
- deterministic replay with input/policy/output hashes
- AI schema and evidence validation
- human approval for material actions
- synthetic-only public demo

## State machine
uploaded → profiling → classifying → reviewing → published → superseded

## Build order
Implement Phases 0–10 in order. Do not skip phase gates. Do not merge phases merely to reach a demo faster.

## Portfolio contract
Feeds classified spend, price baselines and opportunity records to CostPilot, RFQLens and SupplierRadar; can create missions for ProcurementOS.
