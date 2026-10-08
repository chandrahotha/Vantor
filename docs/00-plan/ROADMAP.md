<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ROADMAP - VANTOR build phases

Statuses: `PLANNED / IN DEVELOPMENT / IMPLEMENTED / TESTED / PRODUCTION READY`.
**Nothing is `PRODUCTION READY`.** Phase 10 owns that gate.

**Product count: 10.** Canonical per-product list: [`../01-product/portfolio.md`](../01-product/portfolio.md).

## How to read a status

| Status | Means |
|---|---|
| `TESTED` | Implemented; covered by the automated suite; no mock data on that path |
| `IN DEVELOPMENT` | Partially implemented. **The named gaps are listed - read them before assuming coverage** |
| `PLANNED` | Not started |

An `IN DEVELOPMENT` phase with its gaps written down is honest. A phase marked
`TESTED` with a broken suite is a lie — every count in this file is regenerated
from the code (`python scripts/doc_counts.py --check` fails the build on drift).

## Phase 0 - Discovery [done]
Product scope fixed at 10 products; stack decided (ADR-007: FastAPI).
Gate: PASSING.

## Phase 1 - Product architecture [done]
`docs/01-product/*`, `docs/02-architecture/*`, `docs/03-ai/*`, `docs/04-security/*`, ADRs 001-007.
Keycloak OIDC + RQ/Redis as the identity and queue backbone. Gate: PASSING.

## Phase 2 - Design system [IN DEVELOPMENT - tokens + shipped fonts + dark theme landed, deltas remain]
Landed: 8pt grid, type scale, radius/elevation scales, semantic surfaces/text, `tabular-nums`,
skip link, `:focus-visible`, skeleton shimmer, banner/panel/badge/button/input polish,
Inter + JetBrains Mono shipped via `next/font`, dark theme via `[data-theme="dark"]`
with an OS-preference default + manual toggle, palette + shell redesign.
**Gaps:** tables do not yet support pin/group/saved-views/export — DataTable is the
shared primitive and adds these only behind a feature flag; only `/suppliers` has
sort + search + paging, the other tables are still raw `<table>` with no shared
primitive.
Gate: **PARTIAL.**

## Phase 3 - Foundation [TESTED - 386 pytest collected, PG chain 0001-0029 verified in CI]
Repo structure, Keycloak OIDC, multi-tenancy RLS, RBAC, Postgres migrations, hash-chained audit,
canonical idempotency, rate limiting, security headers, `/api/v1`, honest `/ready`.
Gate: tenant-isolation + auth tests green - **PASSING**.

## Phase 4 - Procurement core [TESTED - supplier→sourcing→contract→purchase→spend, 98 API operations across 84 paths]
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

## Phase 7 - Web UI [IN DEVELOPMENT - 15 routes, 166 vitest green across 13 suites]
Landed: auth splash, search trigger + theme toggle, supplier 360 (contacts/certs/verify/
qualification), contracts (create/status/obligations/sign), requisitions (create/submit),
pricing check trigger, optimizer trigger, governance (audit chain + categories + budgets),
documents (upload/extract/search with mode label), copilot (real SSE + provider status),
notifications (real 30s polling), per-page metadata, authscreen, error/loading/not-found
boundaries.
Gate: **PARTIAL** - page and component tests are green; full automated a11y/perf budgets not yet wired (axe runs in the on-demand Playwright tier only).

## Phase 8 - Integrations [IN DEVELOPMENT - 1 reference adapter, PASSING on its own gate]
Adapter interface (ERP/finance/email/storage/IdP) with no provider hard-coded in core; HMAC-signed
webhooks with delivery log; `secret_ref` must be `env:NAME`; non-HTTPS endpoints refused.
Gate: ≥1 reference adapter + webhook contract tests - **PASSING**.

## Phase 9 - Android [NOT STARTED - strategy only, no app code]
Kotlin + Compose against the same backend; approvals/alerts/RFQ/contract/copilot first.
The API is ready (OIDC + RLS + approvals). Gate: auth + approval E2E on device. **Not started**
— see `../07-android/strategy.md` and `android/README.md`.

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

1. **A number in a doc is a claim.** Every count here is regenerated from the code
   (`python scripts/doc_counts.py --check`), and CI `git diff --exit-code`s the
   OpenAPI contract so drift fails the build.
2. **CI must be able to fail.** Every push and pull request runs the gates; the
   weekly schedule and the on-demand full suite (Postgres + Playwright) add depth.
   Run the gates locally before pushing.
3. **SQLite cannot see RLS bugs.** Application-level tenant filters pass on SQLite and still leak
   on Postgres. Test the invariant structurally when the test DB cannot express it.
4. **Never claim what is not implemented.** Phase 5 has four real stages, not ten.
