# Data Dictionary — Supplier Onboarding & Qualification Agent

## Core entities
| Field key | Entity | Meaning | Tenant-scoped | Identifier type |
|---|---|---|---|---|
| `onboardingcase` | OnboardingCase | supplier onboarding workflow envelope with status, requirement pack and reviewer assignments | yes | UUID |
| `suppliersubmission` | SupplierSubmission | immutable submission snapshot containing submitted profile values and documents | yes | UUID |
| `requirementpack` | RequirementPack | versioned list of mandatory/conditional supplier requirements by region/category | yes | UUID |
| `qualificationchecklist` | QualificationChecklist | generated checklist with rule outcomes and evidence references | yes | UUID |
| `compliancefinding` | ComplianceFinding | missing, expired, contradictory or policy-violating evidence item | yes | UUID |
| `expiryrecord` | ExpiryRecord | document/qualification attribute with issue, expiry and policy reminder dates | yes | UUID |
| `supplierprofilesnapshot` | SupplierProfileSnapshot | reviewed supplier record approved for controlled publication | yes | UUID |
| `requalificationevent` | RequalificationEvent | future workflow trigger based on expiry or periodic review | yes | UUID |

## Cross-cutting field requirements
- `tenant_id`: mandatory on tenant-owned records.
- `id`: UUID; never expose sequential internal ids where enumeration risk exists.
- `created_at`, `updated_at`: timezone-aware timestamps.
- `source_system`: controlled enum for imported/integrated facts.
- `record_version`: optimistic-concurrency/version marker where mutable workflows exist.
- `is_synthetic`: mandatory for demo-seed records.
- monetary values: `amount_minor` + ISO 4217 currency or Decimal representation with exact serialization.
- quantities: `quantity`, `uom_code`, `normalized_quantity`, `conversion_basis_id`.
- evidence-backed values: `source_document_id`, `source_document_version_id`, `evidence_span_id` where applicable.
- analytical results: `input_snapshot_hash`, `policy_version`, `engine_version`, `result_hash`.
