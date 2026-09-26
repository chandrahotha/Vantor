# AI Supplier Negotiation Simulator

**Product ID:** 10  
**Code:** NEGOSIM  
**Mission:** Let procurement professionals rehearse negotiations using structured supplier evidence, cost positions, constraints and simulated counterpart behavior without changing live procurement systems.

## Core inputs
Approved/synthetic supplier facts, RFQLens quotes, CostPilot cost positions, SupplierRadar risk/performance, negotiation objectives and policy limits.

## Core outputs
Negotiation rounds, supplier responses, concession ladder effects, buyer scorecards, post-session debrief and evidence-backed preparation brief.

## Deterministic core
Deterministic negotiation state, concession arithmetic, guardrails and scoring; LLM generates counterpart language inside a constrained simulator sandbox.

## Portfolio integration
Read-only consumers of Products 02, 03 and 05. Can optionally create a draft brief for ProcurementOS, but cannot message suppliers or update live award/contract/PO records.

## Product state machine
`draft → prepared → running → paused → completed / aborted → debriefed → archived`

## Primary screens
- N01 Simulation Dashboard
- N02 Create Simulation
- N03 Evidence Pack
- N04 Buyer Objectives
- N05 Supplier Persona
- N06 Guardrails
- N07 Live Negotiation
- N08 Offer Ledger
- N09 Concession Ladder
- N10 Scenario Branches
- N11 Pressure Tests
- N12 Debrief
- N13 Skill Scorecard
- N14 Preparation Brief
- N15 Session History
- N16 Export

## Key risks
AI persona hallucination, prompt injection through evidence, unstable scoring, user confusing simulation with factual supplier behavior, accidental live integration.

## Build rule
The product must be independently runnable, testable and deployable. Portfolio integrations are optional read/analysis adapters until all approval and material-action gates are satisfied.
