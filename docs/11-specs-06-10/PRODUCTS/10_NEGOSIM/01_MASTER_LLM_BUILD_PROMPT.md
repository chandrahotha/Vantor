# Master LLM Build Prompt — AI Supplier Negotiation Simulator

Build a complete enterprise procurement application, not a prototype.

## Product mission
Let procurement professionals rehearse negotiations using structured supplier evidence, cost positions, constraints and simulated counterpart behavior without changing live procurement systems.

## Architecture
Use the inherited Top-5 architecture and the product-specific deterministic engine. Keep `engine/` pure enough to run golden vectors without the web server or LLM. Keep `ai/` behind explicit interfaces. Use typed Pydantic request/response models and versioned schemas.

## Core inputs
Approved/synthetic supplier facts, RFQLens quotes, CostPilot cost positions, SupplierRadar risk/performance, negotiation objectives and policy limits.

## Core outputs
Negotiation rounds, supplier responses, concession ladder effects, buyer scorecards, post-session debrief and evidence-backed preparation brief.

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
draft → prepared → running → paused → completed / aborted → debriefed → archived

## Build order
Implement Phases 0–10 in order. Do not skip phase gates. Do not merge phases merely to reach a demo faster.

## Portfolio contract
Read-only consumers of Products 02, 03 and 05. Can optionally create a draft brief for ProcurementOS, but cannot message suppliers or update live award/contract/PO records.
