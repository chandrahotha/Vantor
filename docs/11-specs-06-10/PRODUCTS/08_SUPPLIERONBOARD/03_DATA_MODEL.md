# Data Model — Supplier Onboarding & Qualification Agent

## Canonical entities
OnboardingCase, SupplierSubmission, SupplierProfileSnapshot, Document, DocumentVersion, ExtractionField, EvidenceSpan, QualificationRule, QualificationChecklist, ChecklistItem, RequirementPack, ComplianceFinding, ExpiryRecord, ReviewTask, Approval, RequalificationEvent, AIJob, ExportJob, AuditEvent

## Key fields / facts
legal identity, tax identifiers, banking fields, certifications, insurance, ownership declarations, quality data, ESG attestations, document dates, issue/expiry dates, country, commodity scope

## Cross-cutting requirements
- All tenant-owned entities include `tenant_id`.
- Use UUID identifiers.
- Money = integer minor units or Decimal + ISO 4217.
- Quantity = value + UOM + normalized value + conversion provenance/version.
- Every material analytical result stores input snapshot/hash and rules/policy version.
- Evidence records reference immutable document/version and location where applicable.
- Audit records capture actor, action, before/after hashes, request/correlation id and reason where necessary.
- Unique constraints include tenant scope.
- Effective-dated records prevent overlapping active policies where domain rules require it.
