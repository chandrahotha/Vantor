# AI Architecture — Strategic Sourcing Optimization Engine

## Role
AI can explain trade-offs, summarize scenarios and suggest what constraints to inspect. It cannot choose allocations outside the deterministic solver or directly alter constraints/solutions.

## Guardrails
- untrusted input classification
- prompt/content separation
- schema-first structured output
- evidence/reference validation
- model/run ledger
- prompt versioning
- PII/secret masking where applicable
- bounded retries
- AI unavailable fallback
- no direct domain-table writes

## Required AI result metadata
`ai_run_id`, `provider`, `model`, `prompt_version`, `input_hash`, `output_hash`, `started_at`, `completed_at`, `schema_version`, `confidence` when meaningful, `evidence_refs[]` where applicable.
