# Data Dictionary — PO Price Intelligence Engine

## Core entities
| Field key | Entity | Meaning | Tenant-scoped | Identifier type |
|---|---|---|---|---|
| `porecord` | PORecord | purchase order header with supplier, site, currency and policy context | yes | UUID |
| `poline` | POLine | transaction line with ordered quantity, price basis and commercial attributes | yes | UUID |
| `priceobservation` | PriceObservation | historical comparable price point with source and basis | yes | UUID |
| `comparabilityassessment` | ComparabilityAssessment | explicit comparison state plus reasons and missing attributes | yes | UUID |
| `baselinemodel` | BaselineModel | deterministic selected peer set and statistical/threshold method | yes | UUID |
| `priceanomaly` | PriceAnomaly | validated exception with variance, confidence/state and evidence | yes | UUID |
| `leakagecomponent` | LeakageComponent | decomposed financial difference such as unit price, freight, discount or tax | yes | UUID |
| `resolutionaction` | ResolutionAction | documented reviewer disposition or remediation path | yes | UUID |

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
