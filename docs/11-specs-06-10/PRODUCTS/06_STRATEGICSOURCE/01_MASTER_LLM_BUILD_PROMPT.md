# Master LLM Build Prompt — Strategic Sourcing Optimization Engine

Build a complete enterprise procurement application, not a prototype.

## Product mission
Turn procurement requirements, supplier quotes, capacity, risk and policy constraints into explainable, reproducible sourcing allocations.

## Architecture
Use the inherited Top-5 architecture and the product-specific deterministic engine. Keep `engine/` pure enough to run golden vectors without the web server or LLM. Keep `ai/` behind explicit interfaces. Use typed Pydantic request/response models and versioned schemas.

## Core inputs
RFQLens RFQ/quotes, CostPilot should-cost/benchmarks, SupplierRadar risk/performance, supplier capacity, MOQ/lot constraints, geographic or diversification policies.

## Core outputs
Feasible sourcing scenarios, allocation by supplier/item/period, total landed cost, policy violations, sensitivity analysis, explainable decision package.

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
draft → validating → ready → solving → solved / infeasible / failed → approved → archived

## Build order
Implement Phases 0–10 in order. Do not skip phase gates. Do not merge phases merely to reach a demo faster.

## Portfolio contract
Consumes Product 02 RFQLens, Product 03 CostPilot and Product 05 SupplierRadar through contracts. Publishes scenario and solution events to Product 01 ProcurementOS.
