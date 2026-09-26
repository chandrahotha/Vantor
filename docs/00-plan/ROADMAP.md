<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ROADMAP — VANTOR Phases 0–10

Statuses: `PLANNED / IN DEVELOPMENT / IMPLEMENTED / TESTED / VERIFIED / PRODUCTION READY`.
Nothing is `PRODUCTION READY` in V1 scaffold.

## Phase 0 — Discovery [VERIFIED 2026-09-26]
`REPOSITORY_AUDIT.md` filled with evidence (5/5 repos, ~775 files, source SHAs recorded); stack decided (ADR-007: FastAPI). Audit clones deleted; no private code committed. Gate passed: architecture decisions now unblocked.

## Phase 1 — Product architecture [IN DEVELOPMENT — docs drafted]
`docs/01-product/requirements.md`, `docs/02-architecture/*`, `docs/03-ai/*`, `docs/04-security/*`, ADRs. Gate: docs review + stack decision ADR signed.

## Phase 2 — Design system [IN DEVELOPMENT — tokens + logo drafted]
`docs/05-frontend/design-system.md`, `docs/06-brand/logo.md`, `assets/brand/*.svg`. Gate: token + component inventory approved.

## Phase 3 — Foundation [PLANNED]
Repo structure, Keycloak OIDC, multi-tenancy RLS, RBAC, Postgres migrations, audit log, config, `/api/v1` skeleton, CI full gates. Gate: tenant-isolation + auth tests green.

## Phase 4 — Procurement core [PLANNED]
Suppliers, categories, sourcing/RFQ/quotes/award, contracts, requisitions/PO/receipt/invoice, approvals. Gate: E2E P2P flow green with real DB.

## Phase 5 — Intelligence [PLANNED]
Document pipeline (validate→store→OCR→extract→chunk→embed→index→analyze→evidence→review→audit), search, spend analytics. Gate: large-doc + eval accuracy thresholds.

## Phase 6 — AI [PLANNED]
Gateway (Ollama default, free-tier fallbacks), Copilot streaming+citations, typed tools, HITL approvals, eval harness, injection defenses. Gate: eval + red-team pass.

## Phase 7 — Premium UI [PLANNED]
Dashboard (attention + health, real data only), grids, command palette, notifications, realtime where real. Gate: a11y + perf budgets.

## Phase 8 — Integrations [PLANNED]
Adapter framework (ERP/finance/email/storage/IdP); no provider hard-coded in core. Gate: ≥1 reference adapter + webhook contract tests.

## Phase 9 — Android [PLANNED]
Kotlin+Compose, same backend; approvals/alerts/RFQ/contract/copilot first. Gate: auth+approval E2E on device.

## Phase 10 — Production [PLANNED]
Staging→prod promotion, backups/restore drills, load tests, scans, runbooks, incident response. Gate: checklist §55 all VERIFIED.

## Definition of Done (per feature)

`Domain + DB + Backend + AuthZ + Frontend + Validation + Errors + Audit + Tests + Observability + Docs` as appropriate. Screens alone ≠ done.
