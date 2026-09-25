<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# MIGRATION PLAN — 5 repos → 1 VANTOR

**Status: `PLANNED`. Executable only after `REPOSITORY_AUDIT.md` is filled.**

## Classification framework

Every significant component gets one verdict + reason + evidence link:

- **KEEP** — production-sound, move with minimal change (e.g., proven OCR chunker with tests).
- **ADAPT** — good logic, needs tenancy/RBAC/audit wrapper (most AI prompts fall here).
- **MERGE** — duplicated across repos (supplier models, auth, upload) → single canonical module.
- **REFACTOR** — works but unsafe/untestable (raw SQL from AI, hard-coded limits) → typed + tested.
- **REWRITE** — fundamentally unsound or mock/fake (hard-coded suppliers, simulated AI) → rebuild real.
- **DEPRECATE / REMOVE** — dead, duplicated, or dangerous code; record reason, keep ADR trail.

## Provisional mapping (hypotheses to verify)

| Source (assumed) | Target Vantor module | Provisional verdict | Why |
|---|---|---|---|
| SupplierRadar supplier models/scorecards | `supplier/` | ADAPT/MERGE | Canonical supplier domain; add tenant_id, RLS, audit |
| ContractGuard upload/OCR/clause extract | `document/` + `contract/` | ADAPT | Keep pipeline shape (§16); sandbox + evidence citations |
| CostPilot spend/savings math | `spend/` | ADAPT | Keep formulas; add currency normalization + provenance |
| RFQLens RFQ/quote compare | `sourcing/` | MERGE | Single RFQ→Quote→Award flow; kill forks |
| ProcurementOS agent/prompts/tools | `ai/` | REFACTOR | Typed tools + permission checks; no raw SQL/shell |
| Any auth copy in each repo | `identity/` | MERGE | One Keycloak OIDC path only |
| Any hard-coded/fake data | — | REWRITE/REMOVE | Violates non-negotiable §2 |

## Migration waves

1. **Wave 0 — Freeze + inventory:** tag source SHAs, fill audit matrix, mark secrets for rotation (never migrate secrets).
2. **Wave 1 — Foundation:** identity/tenancy/audit/config land first; sources read-only.
3. **Wave 2 — Canonical domains:** supplier → sourcing → contract → spend → purchase, one module at a time with migration tests.
4. **Wave 3 — Intelligence:** document pipeline + embeddings + AI gateway cut over; old prompts quarantined behind eval gate.
5. **Wave 4 — Decommission:** archive forks, update ROADMAP statuses to IMPLEMENTED/TESTED only with proof.

## Data migration principles

- Migrate with versioned SQL migrations + backfill scripts + rollback; soft-delete only where justified.
- Normalize currencies/units/categories; dedupe suppliers via entity resolution; preserve provenance (`source_repo`, `source_commit`).
- No customer/secret data enters public repo history — sanitize before public push.
