<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# MIGRATION PLAN - 5 repos → 1 VANTOR

**Status: `IN DEVELOPMENT` - audit `VERIFIED` 2026-09-26 (see `REPOSITORY_AUDIT.md`). Verdicts below are final per-component judgments with source SHAs; execution starts Phase 3.**

## Decided stack (from audit convergence)

5/5 backends FastAPI → Vantor backend = **FastAPI** (ADR-007). 4/5 frontends Next.js → web = **Next.js**. Queue = **RQ + Redis** (only real specimen: ProcurementOS `worker/queue.py`). Storage = S3-compatible, wired once. Auth = Keycloak OIDC fronting the JWKS-verification pattern proven in ContractGuard/ProcurementOS/CostPilot.

## Final verdicts (source: commit SHAs in `REPOSITORY_AUDIT.md`)

| Source component | Target Vantor module | Verdict | Why |
|---|---|---|---|
| SupplierRadar KPI/scoring/rules engines | `spend/` + `supplier/` scoring | KEEP | Bit-exact deterministic core, 97% coverage, golden-tested |
| SupplierRadar ingest spans + AI 5-validators | `document/` + `ai/` | KEEP | Canonical evidence + narrator-never-calculates pattern for all AI |
| SupplierRadar audit chain + idempotency + PG rate limits | `platform/` | KEEP | Concurrency-correct; adopt as canonical |
| SupplierRadar worker tick | `worker/` | ADAPT | Add retries/DLQ/metrics; migrate jobs onto RQ |
| ContractGuard matching engine | `contract/` matching | KEEP | 11-dim hashed core differentiator, golden-tested |
| ContractGuard auth/MFA/OIDC + RLS + SoD approvals | `identity/` + `approval/` | KEEP | Strongest prod-ready asset; generalize roles to Vantor matrix |
| ContractGuard ingestion (JSON/PDF-text) | `document/` | ADAPT | Add OCR + real clause parser before prod |
| ContractGuard AI explainer | `ai/` | REFACTOR | Keep guardrails; plug real LLM; fix openai/anthropic fallback bug |
| CostPilot calculation engine | `spend/` should-cost | KEEP | Integer-money deterministic moat, golden vectors |
| CostPilot auth + OIDC + audit chain | `identity/` + `platform/` | KEEP | Fail-closed HS256 + asymmetric JWKS above-average maturity |
| CostPilot NEG-004 AI pattern | `ai/` | KEEP | Real HTTP, no-silent-fallback, quarantine-before-approve |
| CostPilot 1300-line router + snapshot store | `spend/` API | REFACTOR | Split router; Postgres relational + RLS as prod default |
| RFQLens normalization/solver/benchmark | `sourcing/` | KEEP | Only defensible sourcing IP; real deterministic math |
| RFQLens RFQ routers + 9-step web flow | `sourcing/` + web | KEEP | Real RFQ→award chain with evidence/SoD gates |
| RFQLens MockAIProvider + synthetic bands + hash costs + `1000000` defaults + `*0` KPIs + worker dummies | - | REWRITE | Only dishonest-as-done code found in audit; collapse to flagged `?demo=true` fixtures or delete |
| RFQLens bespoke Redis queue + drifted migration | `worker/` + migrations | REFACTOR | Adopt RQ (already in its deps); regenerate Alembic from models |
| ProcurementOS FastAPI core + lane quorum + server-computed award | `approval/` + `platform/` | KEEP | Key safety asset; hash-locked quorum pattern |
| ProcurementOS deterministic `engine/` | `spend/` + `supplier/` | KEEP | Decimal-only golden-vectored source of truth |
| ProcurementOS 14-tool closed registry | `ai/` tools | ADAPT | Enforce least privilege; wire 6 remaining `_echo` handlers to real code |
| ProcurementOS RQ worker + compose + migrations | `worker/` + infra | KEEP | Canonical queue + staging-ready container shape |
| ProcurementOS mock-ai default + `quickFill` synthetics + localStorage token | - | REWRITE/REMOVE | Dev doubles must not ship; OIDC session + explicit empty states |
| 5× supplier shapes, 5× document shapes, 5× audit shapes | canonical domain | MERGE | One `supplier/`, one `document/`, one audit writer; provenance columns kept |
| 5× HS256-demo auths, dead `security.get_actor`, legacy `AIProvider` stub, empty `packages/contracts`, terraform-stub, stray `n.md` | - | REMOVE | Dead/duplicate/placeholder; never migrate secrets |

## Migration waves

1. **Wave 0 - Freeze + inventory (DONE):** source SHAs tagged in audit; secrets marked rotate-only, never migrate.
2. **Wave 1 - Foundation:** identity (Keycloak + JWKS pattern) / tenancy RLS / canonical audit+idempotency / config / `/api/v1` skeleton. Sources read-only.
3. **Wave 2 - Canonical domains:** supplier → sourcing (RFQLens chain) → contract (ContractGuard matching) → spend (CostPilot + SupplierRadar engines) → purchase (ProcurementOS actions), one module at a time with migration tests. RFQLens demo paths rewritten, not ported.
4. **Wave 3 - Intelligence:** SupplierRadar span pipeline + embeddings + AI gateway (5-validator pattern) cut over; old prompts quarantined behind eval gate.
5. **Wave 4 - Decommission:** archive forks, update ROADMAP statuses to IMPLEMENTED/TESTED only with proof.

## Data migration principles

- Migrate with versioned SQL migrations + backfill scripts + rollback; soft-delete only where justified.
- Normalize currencies/units/categories; dedupe suppliers via entity resolution; preserve provenance (`source_repo`, `source_commit`).
- No customer/secret data enters public repo history - sanitize before public push.
