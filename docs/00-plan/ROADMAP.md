<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ROADMAP — VANTOR Phases 0–10

Statuses: `PLANNED / IN DEVELOPMENT / IMPLEMENTED / TESTED / VERIFIED / PRODUCTION READY`.
Nothing is `PRODUCTION READY` in V1 scaffold.

## Phase 0 — Discovery [VERIFIED 2026-09-26]
`REPOSITORY_AUDIT.md` filled with evidence (5/5 repos, ~775 files, source SHAs recorded); stack decided (ADR-007: FastAPI). Audit clones deleted; no private code committed. Gate passed: architecture decisions now unblocked.

## Phase 1 — Product architecture [SIGNED 2026-09-26]
`docs/01-product/requirements.md`, `docs/02-architecture/*`, `docs/03-ai/*`, `docs/04-security/*`, ADRs.
Keycloak OIDC + RQ/Redis confirmed against live audit evidence; stack ADR-007 stands. Gate passed.

## Phase 2 — Design system [IN DEVELOPMENT — tokens + logo drafted]
`docs/05-frontend/design-system.md`, `docs/06-brand/logo.md`, `assets/brand/*.svg`. Gate: token + component inventory approved.

## Phase 3 — Foundation [TESTED — 82 pytest green, PG migration chain 0001–0013 verified in CI]
Repo structure, Keycloak OIDC, multi-tenancy RLS, RBAC, Postgres migrations, audit log, config, `/api/v1` skeleton, CI weekly gates. Gate: tenant-isolation + auth tests green — PASSING.

## Phase 4 — Procurement core [TESTED — supplier→sourcing→contract→purchase→spend, 56 API paths]
Suppliers, categories, sourcing/RFQ/quotes/award, contracts, requisitions/PO/receipt/invoice, approvals. Gate: E2E P2P flow green with real DB — PASSING on sqlite unit + PG CI migrate.

## Phase 5 — Intelligence [IN DEVELOPMENT — Wave 1 done: upload/validate/hash/store + chunks schema]
Document pipeline (validate→store→OCR→extract→chunk→embed→index→analyze→evidence→review→audit), search, spend analytics. Gate: large-doc + eval accuracy thresholds.

## Phase 6 — AI [IN DEVELOPMENT — gateway (ollama/opencode/nvidia/disabled) + typed tools + honesty evals done]
Gateway (Ollama default, free-tier fallbacks), Copilot streaming+citations, typed tools, HITL approvals, eval harness, injection defenses. Gate: eval + red-team pass.

## Phase 7 — Premium UI [IN DEVELOPMENT — Wave 1 done: Next.js dashboard + 7 modules + copilot, build green]
Dashboard (attention + health, real data only), grids, command palette, notifications, realtime where real. Gate: a11y + perf budgets.

## Phase 8 — Integrations [IN DEVELOPMENT — Wave 1 done: adapter interface + logging reference + HMAC webhooks]
Adapter framework (ERP/finance/email/storage/IdP); no provider hard-coded in core. Gate: ≥1 reference adapter + webhook contract tests — PASSING.

## Phase 9 — Android [COMING SOON — API-ready, native app starts as its own wave]
Kotlin+Compose, same backend; approvals/alerts/RFQ/contract/copilot first. Gate: auth+approval E2E on device.

## Phase 10 — Production [PLANNED]
Staging→prod promotion, backups/restore drills, load tests, scans, runbooks, incident response. Gate: checklist §55 all VERIFIED.

## Phase 11 — Portfolio extension 06–10 [PLANNED — specs vendored in `docs/11-specs-06-10/`]
Native Vantor modules from the ProcurementAI build-brain, in order `08 → 09 → 07 → 06 → 10`:
onboarding/qualification → PO price intel → spend intel → sourcing optimizer → negotiation simulator.
Each ships with its spec's golden test matrix + acceptance criteria as gates; truth hierarchy holds
(deterministic math = record, AI = advisory until approved). Gate: all five acceptance suites green on real DB.

## Definition of Done (per feature)

`Domain + DB + Backend + AuthZ + Frontend + Validation + Errors + Audit + Tests + Observability + Docs` as appropriate. Screens alone ≠ done.
