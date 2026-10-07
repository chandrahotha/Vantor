<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# AI Architecture - VANTOR (free-first, evidence-first)

**Status: `PLANNED`.**

## Gateway
`AI_PROVIDER` switch: `ollama` (local default, `llama3.1:8b` + `nomic-embed-text`) → `openrouter-free` / `groq-free` / `huggingface` fallbacks via BYO key → `disabled` (deterministic non-AI paths still work). No paid key required for dev; provider limits documented in UI when hit. Token/cost/latency metered per tenant.

## Agent loop (mandatory order)
`User → Intent → Planner → ToolSelection → PermissionValidation → DataRetrieval → EvidenceRetrieval → PolicyValidation → RiskValidation → StructuredOutput → HumanApproval (risk-based) → Action → AuditEvent`. AI has **no** raw SQL/shell/DB access - typed tools only (`../02-architecture/api.md`).

## Evidence contract
Every material answer: `{answer, confidence, evidence[{document_id,page,section,excerpt}], data_timestamp, requires_human_review}`. Missing info → `UNKNOWN / NOT PROVIDED / NEEDS VERIFICATION / REQUIRES SUPPLIER CONFIRMATION`. Hallucinated procurement facts = P0 bug.

## Autonomy tiers
- Auto: summarize, draft RFQ/shortlist, detect anomalies/savings candidates.
- Confirm: send RFQ, share supplier-facing text, create PO draft.
- Explicit approval: award, high-value PO/invoice approval, bank-detail change, irreversible/financial writes (thresholds configurable per org).

## Document intelligence pipeline
`Upload → validate → malware hook → MinIO → OCR (if needed) → extract → classify → chunk → metadata → embed → pgvector index → AI analyze → evidence store → human review → audit`. PDF/DOCX/XLSX/CSV/images/scans; large docs chunked + backgrounded with progress.
