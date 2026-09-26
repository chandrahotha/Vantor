# Master LLM Build Prompt — Supplier Onboarding & Qualification Agent

Build a complete enterprise procurement application, not a prototype.

## Product mission
Turn supplier submissions into structured qualification cases with evidence-backed checks, missing-document detection, risk signals and approval workflows.

## Architecture
Use the inherited Top-5 architecture and the product-specific deterministic engine. Keep `engine/` pure enough to run golden vectors without the web server or LLM. Keep `ai/` behind explicit interfaces. Use typed Pydantic request/response models and versioned schemas.

## Core inputs
Supplier registration forms, certifications, tax documents, bank details, insurance, ESG questionnaires, quality certificates, policies and supporting documents.

## Core outputs
Supplier profile, evidence map, completeness status, qualification scorecard, compliance gaps, approval routing and onboarding decision package.

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
draft → invited → submitted → processing → needs_info → under_review → approved / rejected / expired → requalification_due

## Build order
Implement Phases 0–10 in order. Do not skip phase gates. Do not merge phases merely to reach a demo faster.

## Portfolio contract
Creates/updates supplier master via controlled contract; publishes qualification changes to SupplierRadar and onboarding tasks to ProcurementOS; references ContractGuard rules where applicable.
