# AI Architecture — Procurement Spend Intelligence Agent

## Role
AI can assist classification suggestions, anomaly narratives and opportunity prioritization. Published spend facts remain deterministic/reconciled. Human review gates low-confidence classifications.

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
