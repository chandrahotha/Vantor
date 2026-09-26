<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ROADMAP — VANTOR Phases 0–11

Statuses: `PLANNED / IN DEVELOPMENT / IMPLEMENTED / TESTED / VERIFIED / PRODUCTION READY`.
**Nothing is `PRODUCTION READY`.** Phase 10 owns that gate.

**Product count: 10.** Canonical per-product list: [`../01-product/portfolio.md`](../01-product/portfolio.md).
"Five" in Phase 0 refers to the audited *repository* count (products 01–05), not the product count.

## How to read a status

| Status | Means |
|---|---|
| `VERIFIED` | Claimed, inspected against evidence, independently confirmed |
| `TESTED` | Implemented; covered by the automated suite; no mock data on that path |
| `IN DEVELOPMENT` | Partially implemented. **The named gaps are listed — read them before assuming coverage** |
| `PLANNED` | Not started |

An `IN DEVELOPMENT` phase with its gaps written down is honest. A phase marked
`TESTED` with a broken suite is a lie, which is exactly what this file used to be.

## Phase 0 — Discovery [VERIFIED 2026-09-26]
`REPOSITORY_AUDIT.md` filled with evidence (5/5 repos, ~775 files, source SHAs recorded); stack
decided (ADR-007: FastAPI). Audit clones deleted; no private code committed.
**Scope note: this phase audited 5 repositories. The product is 10 products.** Gate: PASSING.

## Phase 1 — Product architecture [SIGNED 2026-09-26]
`docs/01-product/*`, `docs/02-architecture/*`, `docs/03-ai/*`, `docs/04-security/*`, ADRs 001–007.
Keycloak OIDC + RQ/Redis confirmed against audit evidence. Gate: PASSING.

## Phase 2 — Design system [IN DEVELOPMENT — tokens landed, half the spec is unimplemented]
Landed: 15 colour tokens with correct hex values, type scale, radius scale, `tabular-nums`,
`prefers-reduced-motion`, skip link, global `:focus-visible` ring.
**Gaps:** no dark mode (zero `prefers-color-scheme`); no elevation tokens (the spec's 0/1/2/3
scale is undefined, and `CommandPalette.tsx` hardcodes a shadow); Inter + JetBrains Mono are
declared in CSS but never shipped (no `@font-face`, no `next/font`, no webfont in `public/`);
~28 raw hex literals inside `globals.css` bypass the tokens; spacing breaks the 4pt base.
Gate (token + component inventory approved): **NOT MET** — the component inventory in
`05-frontend/design-system.md` specifies a data-grid with sort/filter/pin/group/saved-views/
export/bulk/keyboard. Only `/suppliers` has sort + search + paging; the other 8 tables are raw
`<table>` with no shared primitive.

## Phase 3 — Foundation [TESTED — 96 pytest green, PG chain 0001–0015 verified in CI]
Repo structure, Keycloak OIDC, multi-tenancy RLS, RBAC, Postgres migrations, hash-chained audit,
canonical idempotency, rate limiting, security headers, `/api/v1`, honest `/ready`.
Gate: tenant-isolation + auth tests green — **PASSING**.

> **Regression fixed 2026-09-26.** `tests/test_global_parity.py` shipped with an
> `IndentationError`, so `pytest` collected **zero** tests and exited non-zero while the README,
> ROADMAP and CHANGELOG all claimed a green suite. CI is weekly-only with no PR trigger, so it
> went unnoticed. Fixed, and `test_no_unpinned_sessions_outside_request_cycle` now guards the
> RLS class of bug that SQLite structurally cannot catch.

## Phase 4 — Procurement core [TESTED — supplier→sourcing→contract→purchase→spend, 75 API operations]
Suppliers + scorecards + certification + qualification, categories + catalog + budgets, RFQ/quote/
award + optimizer, contracts + obligations + e-sign + 11-dim matching, requisitions/PO/receipt/
invoice with 3-way match, tiered approvals + SoD, spend ledger, audit chain verification, webhooks.
Gate: E2E P2P flow green — **PASSING** on sqlite unit tests + PG migration CI.
**Gap:** `POST /requisitions` and `/requisitions/{id}/submit` have no test at the API level.

## Phase 5 — Intelligence [IN DEVELOPMENT — ~30%. 4 of 10 pipeline stages real]
Real: `validate` (filename + magic-byte sniff + size), `store` (hash-addressed, atomic, per-tenant),
`extract` (PDF `Tj`/`TJ` + Flate, DOCX/XLSX via zip+XML, text decode), `chunk` (sliding window),
`audit` (hash-chained).
**Absent:** OCR (no engine bundled; images quarantine honestly), embed (`embedding={}` is a
literal empty dict), semantic index (`ILIKE` only, hardcoded `limit(25)`, no `tsvector`/GIN),
analyze, evidence (`ai_gateway` returns `evidence: []` on all four paths), review.
**Known defects in what does exist:** `extract.pages` counts Flate streams, not pages; the PDF
text layer joins every `Tj` with `\n`, shredding sentences and degrading chunk + search quality;
XLSX reads `sheet1.xml` only. MinIO runs in compose and `S3_*` is in `.env.example`, but **no
code reads them** — storage is local disk only.
Gate (large-doc + eval accuracy thresholds): **NOT MET.**

## Phase 6 — AI [IN DEVELOPMENT — typed tools are strong, streaming is not]
Real: gateway with honest per-provider config probing, typed tool registry with role allowlists
and required-arg validation, HITL file/decide with SoD, injection defenses, adversarial eval.
**Absent / overstated:**
- `/ai/stream` is SSE-**framed**, not provider-streamed. The blocking call completes, then the
  finished string is sliced into 120-char frames. Frames carry `"streamed": false` and the
  docstring says so. Time-to-first-byte equals the non-streaming endpoint.
- `evidence: []` on every gateway path and no evidence refs on tool results, contradicting
  `ai_tools.py`'s own docstring.
- `openrouter-free` / `groq-free` / `huggingface` are advertised in `.env.example` and raise
  "not wired in this wave" if selected.
- No frontend consumer of `/ai/stream`; the copilot calls `/ai/complete`.
- Zero test coverage of the ollama/opencode/nvidia HTTP paths (no keys by design).
Gate (eval + red-team pass): **PARTIAL** — eval and injection suites pass; no real-provider test.

## Phase 7 — Premium UI [IN DEVELOPMENT — 12 of 75 operations reachable, 0 frontend tests]
Landed: 9 routes on real API data only, `Promise.allSettled` dashboard with honest partial-failure
reporting, server-paginated supplier grid with sort + search + palette deep-link, command palette,
notifications feed with polling bell, build + typecheck + lint green.
**Gaps:** every write path is API-only — RFQ create/quote/award, PO approve/send/receipt/invoice,
catalog, budgets, integrations, audit viewer, document extract/search, HITL decide. Zero
`error.tsx` / `loading.tsx` / `not-found.tsx`. No shared table/pager/card primitives (the pager is
written 4×, the Keycloak boot 5×, the grid 9×). Command palette lacks a focus trap.
**Correctness bugs fixed 2026-09-26:** should-cost form defaults guaranteed a 422 on first click;
dashboard summed across currencies then labelled with the first supplier's currency; the
`/notifications` page claimed "Polls every 30s" but did not poll.
Gate (a11y + perf budgets): **NOT MET** — no frontend test runner exists.

## Phase 8 — Integrations [IN DEVELOPMENT — 1 reference adapter, PASSING on its own gate]
Adapter interface (ERP/finance/email/storage/IdP) with no provider hard-coded in core; HMAC-signed
webhooks with delivery log; `secret_ref` must be `env:NAME`; non-HTTPS endpoints refused.
Gate: ≥1 reference adapter + webhook contract tests — **PASSING**.

## Phase 9 — Android [NOT STARTED — `android/` does not exist]
Kotlin + Compose against the same backend; approvals/alerts/RFQ/contract/copilot first.
The API is ready (OIDC + RLS + approvals). Gate: auth + approval E2E on device. **0 of 100.**

## Phase 10 — Production hardening [PLANNED — ~10%]
Backup/restore scripts exist (`scripts/backup.ps1`, `scripts/restore.ps1`) and the runbook
documents health, backup and incident response. **Missing:** no OTEL/Prometheus/Sentry (zero
references), no load tests, no staging promotion path, no TLS story, no container scanning, no
restore drill. Gate: checklist §55 all VERIFIED. **NOT MET.**

## Phase 11 — Portfolio extension 06–10 [IN DEVELOPMENT — engines landed, acceptance suites not run]
Native modules in the decided order `08 → 09 → 07 → 06 → 10`:
supplier qualification (08) · PO price intel (09) · spend intel (07) · sourcing optimizer (06) ·
negotiation simulator (10).
Each has a deterministic engine with golden-vector tests (`test_onboarding`, `test_price_intel`,
`test_spend_intel`, `test_optimizer`, `test_negosim`). Specs are vendored read-only in
[`../11-specs-06-10/`](../11-specs-06-10/README.md).
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
