# Data Dictionary — Strategic Sourcing Optimization Engine

## Core entities
| Field key | Entity | Meaning | Tenant-scoped | Identifier type |
|---|---|---|---|---|
| `sourcingevent` | SourcingEvent | business sourcing event with objective, period, status, policy pack and source snapshot hashes | yes | UUID |
| `requirementline` | RequirementLine | item/category requirement with quantity, UOM, site, period and service constraints | yes | UUID |
| `supplieroption` | SupplierOption | eligible supplier offer with capacity, price basis, minimums and eligibility state | yes | UUID |
| `constraint` | Constraint | hard or soft constraint with type, severity, parameters and policy version | yes | UUID |
| `optimizationrun` | OptimizationRun | immutable run request containing frozen source snapshots, model version and solver configuration | yes | UUID |
| `optimizationsolution` | OptimizationSolution | validated solver output with objective value, feasibility result, result hash and allocations | yes | UUID |
| `allocation` | Allocation | supplier × item × period allocation quantity/value plus constraint utilization | yes | UUID |
| `sensitivityrun` | SensitivityRun | controlled change to one or more assumptions producing comparable scenario deltas | yes | UUID |

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
