# Data Dictionary — Procurement Spend Intelligence Agent

## Core entities
| Field key | Entity | Meaning | Tenant-scoped | Identifier type |
|---|---|---|---|---|
| `spendbatch` | SpendBatch | immutable ingestion batch with source system, period, row count and profile status | yes | UUID |
| `spendtransaction` | SpendTransaction | normalized transaction fact retaining source values and canonical dimensions | yes | UUID |
| `supplierentity` | SupplierEntity | canonical supplier identity with source aliases and match confidence | yes | UUID |
| `categorynode` | CategoryNode | versioned category taxonomy node | yes | UUID |
| `classificationresult` | ClassificationResult | candidate/confirmed category and confidence with evidence or matching basis | yes | UUID |
| `spendcubesnapshot` | SpendCubeSnapshot | published aggregate snapshot defined by batch set, taxonomy and normalization version | yes | UUID |
| `leakagefinding` | LeakageFinding | deterministic price/contract/process anomaly tied to transactions and baseline | yes | UUID |
| `savingsopportunity` | SavingsOpportunity | opportunity with baseline, target basis, estimated gross/net savings and confidence | yes | UUID |
| `reviewtask` | ReviewTask | human queue item for low-confidence classification, entity match or opportunity validation | yes | UUID |

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
