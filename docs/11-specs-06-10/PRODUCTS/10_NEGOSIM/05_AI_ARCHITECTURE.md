# AI Architecture — AI Supplier Negotiation Simulator

## Role
AI is the simulator counterpart voice, not the source of truth. It receives a sanitized evidence pack and a constrained persona contract. It cannot invoke production procurement tools.

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
