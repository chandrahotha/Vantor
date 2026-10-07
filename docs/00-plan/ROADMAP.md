<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ROADMAP - VANTOR Phases 0-11

Statuses: `PLANNED / IN DEVELOPMENT / IMPLEMENTED / TESTED / VERIFIED / PRODUCTION READY`.
**Nothing is `PRODUCTION READY`.** Phase 10 owns that gate.

**Product count: 10.** Canonical per-product list: [`../01-product/portfolio.md`](../01-product/portfolio.md).
"Five" in Phase 0 refers to the audited *repository* count (products 01-05), not the product count.

## How to read a status

| Status | Means |
|---|---|
| `VERIFIED` | Claimed, inspected against evidence, independently confirmed |
| `TESTED` | Implemented; covered by the automated suite; no mock data on that path |
| `IN DEVELOPMENT` | Partially implemented. **The named gaps are listed - read them before assuming coverage** |
| `PLANNED` | Not started |

An `IN DEVELOPMENT` phase with its gaps written down is honest. A phase marked
`TESTED` with a broken suite is a lie, which is exactly what this file used to be.

## Phase 0 - Discovery [VERIFIED 2026-09-26]
`REPOSITORY_AUDIT.md` filled with evidence (5/5 repos, ~775 files, source SHAs recorded); stack
decided (ADR-007: FastAPI). Audit clones deleted; no private code committed.
**Scope note: this phase audited 5 repositories. The product is 10 products.** Gate: PASSING.

## Phase 1 - Product architecture [SIGNED 2026-09-26]
`docs/01-product/*`, `docs/02-architecture/*`, `docs/03-ai/*`, `docs/04-security/*`, ADRs 001-007.
Keycloak OIDC + RQ/Redis confirmed against audit evidence. Gate: PASSING.

## Phase 2 - Design system [IN DEVELOPMENT - tokens + shipped fonts + dark theme landed, deltas remain]
Landed: 8pt grid, type scale, radius/elevation scales, semantic surfaces/text, `tabular-nums`,
skip link, `:focus-visible`, skeleton shimmer, banner/panel/badge/button/input polish.
**Landed 2026-09-26:** Inter + JetBrains Mono now actually shipped via `next/font` (they were
declared in CSS but never delivered), dark theme via `[data-theme="dark"]` with an
OS-preference default + manual toggle, palette + shell redesign.
**Gap:** tables do not yet support pin/group/saved-views/export - DataTable is the shared
primitive and adds these only behind a feature flag.
Gate: **PARTIAL.**
Landed: 15 colour tokens with correct hex values, type scale, radius scale, `tabular-nums`,
`prefers-reduced-motion`, skip link, global `:focus-visible` ring.
**Gaps:** no dark mode (zero `prefers-color-scheme`); no elevation tokens (the spec's 0/1/2/3
scale is undefined, and `CommandPalette.tsx` hardcodes a shadow); Inter + JetBrains Mono are
declared in CSS but never shipped (no `@font-face`, no `next/font`, no webfont in `public/`);
~28 raw hex literals inside `globals.css` bypass the tokens; spacing breaks the 4pt base.
Gate (token + component inventory approved): **NOT MET** - the component inventory in
`05-frontend/design-system.md` specifies a data-grid with sort/filter/pin/group/saved-views/
export/bulk/keyboard. Only `/suppliers` has sort + search + paging; the other 8 tables are raw
`<table>` with no shared primitive.

## Phase 3 - Foundation [TESTED - 96 pytest green, PG chain 0001-0015 verified in CI]
Repo structure, Keycloak OIDC, multi-tenancy RLS, RBAC, Postgres migrations, hash-chained audit,
canonical idempotency, rate limiting, security headers, `/api/v1`, honest `/ready`.
Gate: tenant-isolation + auth tests green - **PASSING**.

> **Regression fixed 2026-09-26.** `tests/test_global_parity.py` shipped with an
> `IndentationError`, so `pytest` collected **zero** tests and exited non-zero while the README,
> ROADMAP and CHANGELOG all claimed a green suite. CI is weekly-only with no PR trigger, so it
> went unnoticed. Fixed, and `test_no_unpinned_sessions_outside_request_cycle` now guards the
> RLS class of bug that SQLite structurally cannot catch.

## Phase 4 - Procurement core [TESTED - supplier→sourcing→contract→purchase→spend, 75 API operations]
Suppliers + scorecards + certification + qualification, categories + catalog + budgets, RFQ/quote/
award + optimizer, contracts + obligations + e-sign + 11-dim matching, requisitions/PO/receipt/
invoice with 3-way match, tiered approvals + SoD, spend ledger, audit chain verification, webhooks.
Gate: E2E P2P flow green - **PASSING** on sqlite unit tests + PG migration CI.
**Gap:** `POST /requisitions` and `/requisitions/{id}/submit` have no test at the API level.

## Phase 5 - Intelligence [IN DEVELOPMENT - ingest/keyword/rank real; OCR still absent]
Real: validate, store, extract (PDF/DOCX/XLSX/multi-sheet/CSV), chunk, embed (ollama real
/ toy deterministic / disabled honest fallback), cosine re-rank with `mode: semantic|keyword`,
audit; the extract endpoint is role-gated and idempotent (200), with per-chunk vector counts.
**Still absent:** OCR, analyze/evidence/review workflows. The pgvector HNSW index
(migration `0022_pgvector_embeddings`) is in place - the gap is the OCR/eval loop, not the index.
Gate: **NOT MET** for large-doc + eval accuracy - embedding correctness is covered, the larger
OCR/eval loop is not.

## Phase 6 - AI [IN DEVELOPMENT - gateway + typed tools + HITL + real streaming since 2026-09-26]
Real: gateway with providers probed via env, typed tools with role allowlists + required-arg
validation, human-in-the-loop file/decide with SoD, injection defenses, eval.
**Landed 2026-09-26:** `/ai/stream` is real provider-side streaming for ollama/opencode/nvidia
(the disabled deterministic path is explicit about not being live), `streamed: true/false`
is emitted on every frame, and streamed completions are audited.
**Gap:** evidence refs on tool calls remain empty in the response envelope; that is next.
Gate: **PARTIAL** - streaming now live; real LLM eval still pending.

## Phase 7 - Premium UI [IN DEVELOPMENT - surfaces up to ~46 operations, tests green]
Landed: auth splash, search trigger + theme toggle, supplier 360 (contacts/certs/verify/
qualification), contracts (create/status/obligations/sign), requisitions (create/submit),
pricing check trigger, optimizer trigger, governance (audit chain + categories + budgets),
documents (upload/extract/search with mode label), copilot (real SSE + provider status),
notifications (real 30s polling), per-page metadata, authscreen, error/loading/not-found
boundaries. 35 component + unit tests.
Gate: **PARTIAL** - smoke/gate tests are green; full automated a11y/perf budgets not yet wired.

## Phase 8 - Integrations [IN DEVELOPMENT - 1 reference adapter, PASSING on its own gate]
Adapter interface (ERP/finance/email/storage/IdP) with no provider hard-coded in core; HMAC-signed
webhooks with delivery log; `secret_ref` must be `env:NAME`; non-HTTPS endpoints refused.
Gate: ≥1 reference adapter + webhook contract tests - **PASSING**.

## Phase 9 - Android [NOT STARTED - `android/` does not exist]
Kotlin + Compose against the same backend; approvals/alerts/RFQ/contract/copilot first.
The API is ready (OIDC + RLS + approvals). Gate: auth + approval E2E on device. **0 of 100.**

## Phase 10 - Production hardening [IN DEVELOPMENT - monitoring wired, drills pending]
Backup/restore scripts (`scripts/backup.ps1`, `scripts/restore.ps1`), structured access logging
with request-ID, **role-gated `/api/v1/ops/metrics`** (in-process request/latency counters),
health + readiness endpoints, RLS session discipline documented, weekly CI, secret guard,
`pip-audit --strict` + `npm audit --audit-level=high`, Dependabot scanning.
**Still due:** OTEL tracing, Prometheus/Grafana dashboard, automated load test, restore drill,
staging-to-prod promotion recipe, container scanning, threat-model red team.
Gate: **NOT MET** - monitoring partially wired; no production-grade drills yet.

## Phase 11 - Portfolio extension 06-10 [IN DEVELOPMENT - engines landed, acceptance suites not run]
Native modules in the decided order `08 → 09 → 07 → 06 → 10`:
supplier qualification (08) · PO price intel (09) · spend intel (07) · sourcing optimizer (06) ·
negotiation simulator (10).
Each has a deterministic engine with golden-vector tests (`test_onboarding`, `test_price_intel`,
`test_spend_intel`, `test_optimizer`, `test_negosim`). The original vendor spec bundle has been
retired; [`../01-product/portfolio.md`](../01-product/portfolio.md) is the canonical per-product
reference.
**Gaps:** no product's full spec acceptance suite has been run, and none has UI. The truth
hierarchy holds throughout (deterministic math = record, AI = advisory until approved).
Gate: all five acceptance suites green on real DB. **NOT MET.**

## Definition of Done (per feature)

`Domain + DB + Backend + AuthZ + Frontend + Validation + Errors + Audit + Tests + Observability + Docs` as appropriate. Screens alone ≠ done.

## Reporting rules (learned the hard way)

1. **A number in a doc is a claim.** 82 tests, 56 routes, "Next.js 14" were all true once and
   quietly stopped being true. Every count here is regenerated from the code, and CI now
   `git diff --exit-code`s the OpenAPI contract so drift fails the build.
2. **CI that cannot fail is worse than no CI.** Weekly-only with no PR trigger let a
   collection-time `IndentationError` ship behind a green badge. Run the gates locally.
3. **SQLite cannot see RLS bugs.** Application-level tenant filters pass on SQLite and still leak
   on Postgres. Test the invariant structurally when the test DB cannot express it.
4. **Never claim what is not implemented.** Phase 5 has four real stages, not ten.
