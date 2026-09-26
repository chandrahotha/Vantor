# Data Dictionary — AI Supplier Negotiation Simulator

## Core entities
| Field key | Entity | Meaning | Tenant-scoped | Identifier type |
|---|---|---|---|---|
| `simulation` | Simulation | immutable high-level scenario with source snapshot ids and policy guardrails | yes | UUID |
| `evidencepack` | EvidencePack | sanitized read-only facts supplied to simulator | yes | UUID |
| `buyerobjective` | BuyerObjective | target/walk-away/priority configuration | yes | UUID |
| `supplierpersona` | SupplierPersona | bounded fictional counterpart model and behavioral parameters | yes | UUID |
| `negotiationround` | NegotiationRound | turn-level state with offers and generated response | yes | UUID |
| `offer` | Offer | deterministic commercial position with timestamp and actor type | yes | UUID |
| `concession` | Concession | difference between positions categorized by issue | yes | UUID |
| `simulationscore` | SimulationScore | post-session rubric results by skill dimension | yes | UUID |
| `debrief` | Debrief | structured learning output with source facts versus generated coaching clearly separated | yes | UUID |

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
