# Master LLM Build Prompt — PO Price Intelligence Engine

Build a complete enterprise procurement application, not a prototype.

## Product mission
Compare PO pricing against clean historical baselines, peer purchases, contract terms and cost/market context to identify explainable commercial anomalies.

## Architecture
Use the inherited Top-5 architecture and the product-specific deterministic engine. Keep `engine/` pure enough to run golden vectors without the web server or LLM. Keep `ai/` behind explicit interfaces. Use typed Pydantic request/response models and versioned schemas.

## Core inputs
PO lines, supplier/item master, UOM/currency, contract prices, price history, freight/discount/tax/incoterm context, category benchmarks.

## Core outputs
Comparable price baseline, anomaly state, variance decomposition, leakage amount, evidence, workflow case and optional negotiation/sourcing handoff.

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
new → normalizing → comparable → analyzed → exception / clear → accepted / dismissed → closed

## Build order
Implement Phases 0–10 in order. Do not skip phase gates. Do not merge phases merely to reach a demo faster.

## Portfolio contract
Consumes ContractGuard contract/PO facts and CostPilot history/baselines. Feeds anomalies to ProcurementOS missions and CostPilot negotiation preparation.
