# Supplier Onboarding & Qualification Agent

**Product ID:** 08  
**Code:** SUPPLIERONBOARD  
**Mission:** Turn supplier submissions into structured qualification cases with evidence-backed checks, missing-document detection, risk signals and approval workflows.

## Core inputs
Supplier registration forms, certifications, tax documents, bank details, insurance, ESG questionnaires, quality certificates, policies and supporting documents.

## Core outputs
Supplier profile, evidence map, completeness status, qualification scorecard, compliance gaps, approval routing and onboarding decision package.

## Deterministic core
Deterministic checklist/rules/expiry validation plus evidence indexing; AI for extraction, summarization and gap explanation only.

## Portfolio integration
Creates/updates supplier master via controlled contract; publishes qualification changes to SupplierRadar and onboarding tasks to ProcurementOS; references ContractGuard rules where applicable.

## Product state machine
`draft → invited → submitted → processing → needs_info → under_review → approved / rejected / expired → requalification_due`

## Primary screens
- O01 Onboarding Queue
- O02 Supplier Invitation
- O03 Registration Workspace
- O04 Document Intake
- O05 Evidence Viewer
- O06 Data Extraction Review
- O07 Qualification Checklist
- O08 Risk & Compliance
- O09 Missing Information
- O10 Reviewer Workspace
- O11 Approval
- O12 Supplier Profile
- O13 Requalification Calendar
- O14 Audit Trail
- O15 AI Activity
- O16 Export

## Key risks
malicious documents/prompt injection, personal/bank data leakage, duplicate supplier records, expired certificates, false approvals.

## Build rule
The product must be independently runnable, testable and deployable. Portfolio integrations are optional read/analysis adapters until all approval and material-action gates are satisfied.
