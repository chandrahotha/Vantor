<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# REPOSITORY AUDIT - VANTOR

**Status: `VERIFIED` - all 5 private repos cloned to `_audit/` (gitignored), inspected read-only, matrix filled with evidence. Clones deleted after audit; no private code committed.**

Audited 2026-09-26. Source SHAs recorded per repo below. ~775 tracked files inspected total.

## Audit matrix

| Repository | Technology | Features (real) | Reusable | Refactor | Rewrite | Risk |
|---|---|---|---|---|---|---|
| SupplierRadar-Valtrix (`9df7da9`, 170 files) | Python 3.12, FastAPI, SQLAlchemy+Alembic, PG15, no frontend | suppliers/sites/items, POs/receipts/QC, KPI/scoring/rules engines, scoring matview, ingest+evidence spans, stub AI narration, hash-chained audit, idempotency, PG rate limits | deterministic engines, ingest spans, AI validators, audit+idempotency, compose | worker (retries/DLQ), exports (renderer+secret split), CI push gates | web app (absent), seeds, terraform-stub | P0 secrets/OIDC absent; malware scan missing; schedule-only CI |
| ContractGuard-Veridox (`b17f430`, 144 files) | Python 3.13 FastAPI + Next.js 16/React 19, SQLite dev/PG prod | compliance cases, deterministic 11-dim matching, exceptions/SLA, dual-control approvals, XLSX/PDF exports, webhooks, MFA/TOTP, OIDC JWKS, RLS | matching engine, auth/MFA/OIDC+RLS+audit, approvals, exports | ingestion (needs OCR), AI explainer (real LLM), webhooks (queued), CI gates | `packages/contracts` (empty), Redis/S3 wiring, dead `security.get_actor` | dev-token/secret defaults must flip; no worker/queue; weekly CI |
| CostPilot-Costryn (`80aea31`, 104 files) | Python ≥3.11 FastAPI + Next.js 16, snapshot JSON/PG, no Docker | cost models, should-cost engine (integer money), gap/UOM/target/ladder/sensitivity/history math, talk-track AI w/ 4-gate validation, PDF/CSV/MD export, OIDC, hash-chained audit | calculation engine, auth+OIDC, AI NEG-004 pattern, exporter, ingestion proposals | 1300-line router split, persistence → relational RLS, CI PR gate | dead `AIProvider` stub, recharts dep, prod runtime (no Dockerfile) | JSON single-process store; no worker; build-time API URL; weekly CI |
| RFQLens-QuotientX (`b14293c`, 152 files) | Python 3.12 FastAPI + Next.js 16, PG15+Redis7+MinIO declared | RFQ→award chain, normalization engine, OR-Tools solver, benchmark bands, comparison views, 9-step web flow, lease worker, approvals w/ SoD | normalization/solver/benchmark engines, RFQ routers, 9-step flow | worker (use celery/rq in deps), Alembic regen from models, CI re-enable | demo-data paths (mock provider, synthetic bands, `1000000` defaults, dashboard `*0` KPIs) | CI file DISABLED; anon-auth flag; S3/MinIO unwired; FX/ECB spec-only |
| ProcurementOS-Agent (`2c9e6c6`, 205 files) | Python ≥3.12 FastAPI async + Next.js 16, PG16+RQ/Redis+MinIO | mission state-machine, 10-step plan DAG, 14-tool closed registry, lane-separated approval quorum, server-computed award value, quarantine ingest, RQ worker, exports | FastAPI core+RBAC+quorum, deterministic `engine/`, tool registry pattern, RQ worker, schema+migrations, compose | 6 `_echo` tools → real handlers, AI prompt versioning, web token → OIDC session, CI push triggers | mock-ai compose svc as prod default, `quickFill` synthetics | weekly CI; staging checklist unchecked; e2e on sqlite not PG |

## Cross-repo findings (evidence-backed)

**Stack convergence (decisive):** 5/5 backends are **Python FastAPI**; 4/5 frontends are **Next.js App Router**; 4/5 target **Postgres** (one snapshot-JSON). Decision: Vantor backend = **FastAPI** (NestJS hypothesis rejected - see `../10-decisions/ADR-007-fastapi-backend.md`), frontend = Next.js, primary DB = Postgres + RLS. Canonical queue = **RQ + Redis** (only ProcurementOS has a real one); canonical object storage = S3-compatible (declared in 4/5, actually wired in ~1 - must wire once, properly).

**Real IP worth keeping:** deterministic money/math engines in all 5 (SupplierRadar scoring, ContractGuard matching, CostPilot should-cost, RFQLens solver, ProcurementOS engine) - all golden-tested, all KEEP. AI safety patterns converge: narrator-never-calculates + evidence fences + validators (SupplierRadar's 5-validator pipeline is the best specimen → canonical). Auth converges on HS256-demo + real OIDC JWKS in 3/5 (ContractGuard, CostPilot, ProcurementOS) → adopt JWKS pattern, front with Keycloak.

**Honesty check:** 4/5 repos are honest about stubs (explicit demo gates, `deterministic` labels, dues ledgers). **RFQLens is the exception**: `MockAIProvider`, synthetic benchmark bands, hash-derived solver costs, worker dummy totals, and `1000000` web defaults can render as real data - flagged **REWRITE** for all demo-data paths before merge.

**Systemic gaps (apply to Vantor build):** CI is weekly-only / disabled everywhere (zero push/PR signal) → Vantor CI must gate PRs from day one. No observability anywhere (no OTEL/Prometheus/Sentry) → Phase 10 must add. Secrets/OIDC-prod wiring unfinished everywhere → Keycloak + secret manager are foundation, not later. No malware scanning, no backup/restore, no TLS stories → production checklist items.

## Consolidation direction (detail in `MIGRATION_PLAN.md`)

KEEP the 5 deterministic cores + safety/audit patterns; ADAPT auth (unify on Keycloak-backed OIDC JWKS), workers (unify on RQ), storage (wire S3 once); MERGE the 5 supplier/document/audit shapes into one domain; REFACTOR the 2 god-router files + AI fallbacks; REWRITE RFQLens demo-data paths + all missing pieces (web for SupplierRadar, prod runtime for CostPilot); REMOVE dead stubs, empty contract packages, terraform placeholders.
