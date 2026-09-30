<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# VANTOR — Intelligent Procurement Operating System

[![CI: on push and PR](https://img.shields.io/badge/CI-push%20%2B%20PR-brightgreen.svg)](.github/workflows/ci.yml)
[![Tests: 362 backend + 152 frontend](https://img.shields.io/badge/tests-362%20backend%20%2B%20152%20frontend-brightgreen.svg)](backend/tests/)
[![API: 95 operations](https://img.shields.io/badge/API-95%20operations-blue.svg)](api/openapi.json)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Backend: FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)](backend/)
[![Frontend: Next.js](https://img.shields.io/badge/frontend-Next.js-black.svg)](frontend/)
[![Auth: local or OIDC](https://img.shields.io/badge/auth-local%20or%20OIDC-orange.svg)](docs/04-security/architecture.md)
[![DB: Postgres RLS](https://img.shields.io/badge/db-Postgres%20RLS-336791.svg)](docs/02-architecture/database.md)
[![CI: weekly](https://img.shields.io/badge/CI-weekly-yellow.svg)](.github/workflows/ci.yml)
[![Docs: brain-linked](https://img.shields.io/badge/docs-brain--linked-6c47ff.svg)](docs/BRAIN.md)

> **Value. Intelligence. Control.**
> Built by **Digi Tracks**. For enquiries: **digi.tracks@outlook.com**.

VANTOR is a unified, production-grade procurement operating system merging **ten** procurement products into one coherent platform.

| # | Product | VANTOR module | Status |
|---|---|---|---|
| 01 | ProcurementOS Agent | AI gateway + typed tool registry + HITL approvals | `TESTED` |
| 02 | RFQLens — RFQ → sourcing decision | `sourcing/` RFQ→quote→award + split optimizer | `TESTED` |
| 03 | CostPilot — should-cost + negotiation intelligence | `spend/` should-cost engine + price intel | `TESTED` |
| 04 | ContractGuard — contract → PO → invoice compliance | `contracts/` + 11-dim matching + e-sign | `TESTED` |
| 05 | SupplierRadar — supplier risk intelligence | `suppliers/` + scorecards + qualification | `TESTED` |
| 06 | Strategic Sourcing Optimization | `sourcing/` optimizer (share-capped allocation) | `TESTED` |
| 07 | Procurement Spend Intelligence | `spend/` cube, leakage, maverick, concentration | `TESTED` |
| 08 | Supplier Onboarding & Qualification | `suppliers/` certs→scorecard→SoD decision | `TESTED` |
| 09 | PO Price Intelligence | `spend/` median baseline + anomaly cases | `TESTED` |
| 10 | AI Supplier Negotiation Simulator | `ai/` concession ladder + walk-away floor | `TESTED` |

Canonical list with per-product detail: **[`docs/01-product/portfolio.md`](docs/01-product/portfolio.md)**.

> Products 01–05 came from the five private repositories audited in Phase 0
> ([`docs/00-plan/REPOSITORY_AUDIT.md`](docs/00-plan/REPOSITORY_AUDIT.md)). Products 06–10
> arrived later as a vendored build-brain
> ([`docs/11-specs-06-10/`](docs/11-specs-06-10/README.md)). "Five" in older docs refers to
> the **audit scope**, never the product count.

> **One-stop procurement:** supplier discovery, onboarding, scorecards, risk, sourcing projects, RFI/RFQ/RFP, quotations, bid evaluation, awards, contracts, obligations, renewals, requisitions, purchase orders, goods receipt, invoices, spend analytics, savings tracking, approvals, workflows, documents, AI copilot, integrations, and mobile approvals — every activity cited with evidence and audit.

**Status.** Backend: 362 pytest passing, 7 skipped (the PostgreSQL tier, which needs `PG_TEST_DATABASE_URL`), 95 API operations. Web: 152 vitest passing across 13 suites, 19 compiled routes, 0 axe violations across all routes in both themes. Worker scheduler: 31 tests.

Not `PRODUCTION READY`, and two qualifications matter more than the counts:

- Until recently `tests/test_e2e_workflow.py` — the one test that walks a whole
  procurement day and is what "all 10 products verified" rested on — **failed on
  a clean checkout**. The audit chain reported itself broken after nothing but
  legitimate activity, because the chain was written in one order and verified
  in another (see `backend/app/services/audit.py`). It passes now, and
  `test_audit_chain.py` pins the regression, but the badge above was green
  while that was true, so treat historical `TESTED` markers as "has tests",
  not "was passing".
- The PostgreSQL tier is skipped by default. Row-level security, the composite
  foreign keys and the pgvector index are only exercised when you point
  `PG_TEST_DATABASE_URL` at a real Postgres. The default run does not cover them.

## Why VANTOR

Procurement teams juggle suppliers, RFQs, quotes, contracts, POs, invoices, spend, risk, and savings across disconnected tools. VANTOR connects them in one **Procurement Graph**:

```
SUPPLIERS → SOURCING → RFQs → QUOTES → NEGOTIATION → CONTRACTS → PURCHASES → INVOICES → SPEND → PERFORMANCE → RISK → SAVINGS
```

with `PROCUREMENT AI + HUMAN + AI COLLABORATION` on top — every AI answer cited with evidence, confidence, and human-review gates.

## What works today (tested, no mocks)

- [x] Backend API (FastAPI, 95 operations, 362 pytest passing): suppliers + scorecards + onboarding + qualification decide, RFQ→quote→award + share-capped optimizer, contracts + obligations + e-sign + matching, requisitions→PO→receipt→invoice with 3-way match, tiered approvals + SoD + budgets, spend ledger + intelligence + should-cost + price cases (per-currency), catalogs, documents + extraction/embeddings/search (keyword + cosine re-rank, honest mode label), notifications (per-recipient read, real polling), AI gateway + typed tools + HITL + negotiation sim, webhooks
- [x] AuthN/Z: two modes, same verification path. **`AUTH_MODE=local` (default)** makes the API its own issuer — it holds an RSA keypair and mints RS256 tokens, so the product runs with no identity service at all. It is **passwordless**: `POST /api/v1/auth/session` issues a session to whoever asks, which means *anyone who can reach the deployment is the operator*. That is the deliberate trade for a one-container deploy; do not expose such a deployment to an untrusted network. **`AUTH_MODE=oidc`** requires Keycloak as before. In both modes the token is signed, carries a tenant, expires, and is verified identically — a forged or foreign-signed token is a 401, which `tests/test_local_auth.py` asserts. Plus RLS tenant isolation (Postgres only), RBAC, hash-chained audit, idempotency, rate limiting, security headers and an honest `/ready`. The `DISABLE_AUTH=1` escape hatch — which returned a full-Admin actor with no token, in every environment, under a docstring saying no such branch existed — has been removed.
- [x] Web app (Next.js 16 / React 19, 15 routes): dashboard, suppliers grid + supplier 360, requisitions, RFQs + comparison + award, contracts, orders (+ PO price check + optimizer trigger), spend (cube/leakage/maverick/should-cost + cases), documents, governance (audit chain + catalog + budgets), integrations, negosim, notifications, copilot (tool-grounded with evidence), command palette (`Ctrl+K`), dark theme, error/loading/not-found boundaries
- [x] Worker (RQ + Redis + beat scheduler), free-only local stack (`docker compose up`), CI: weekly gates by design + per-push lint/typecheck/vitest/pytest + Alembic PG migration chain + OpenAPI drift check + pip-audit + npm audit, load-test script (`backend/scripts/load_test.py`)
- [ ] Real-world providers live-checks: OCR engine not shipped, native pgvector index migration pending (cosine re-rank in-Python is the current honest path), full Phase 11 vendor matrices not yet run, deeper HITL contract chain pending, realtime push (notifications poll), Android app (Phase 9, not started)

Phase 0 audit `VERIFIED`. All 10 products `TESTED` on core paths. Phase 10 Production hardening is `IN DEVELOPMENT` (monitoring wired; restore drills and OTEL pending). Phase 9 Android is `PLANNED`/0 code. `docs/00-plan/PRODUCTION_READINESS.md` has the exact remaining work evidence table.

## Quickstart

### Run it in one container (SQLite, no identity service)

```bash
docker build -t vantor .
docker run -p 8080:8080 -v vantor-data:/data vantor
```

Open **http://localhost:8080** and press **Log in to VANTOR**. There is no
password: this mode issues a session to whoever asks, so *anyone who can reach
the URL is the operator*. It is meant for local use and single-operator
deployments, not for an untrusted network.

The volume holds the database, the uploads and the session signing key. Without
it every restart is a fresh install and every open session is invalidated.

What this mode does not give you, stated up front rather than discovered later:
SQLite has no row-level security, so tenant isolation rests on the query layer
alone — single tenant only; and with no Redis there is no worker and no
scheduler, so nothing that depends on background execution runs.

### Run the pieces separately (development)

```powershell
# API — SQLite file, schema created on first boot
cd backend
python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
$env:DATABASE_URL="sqlite:///./data/vantor.db"
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

```powershell
# Web
cd frontend
npm ci
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"
npm run dev
```

Open **http://localhost:3000** and press **Log in to VANTOR**.

### Run the full stack (Postgres, Redis, worker, Keycloak)

```bash
docker compose up
```

This is the multi-tenant configuration: Postgres enforces tenant isolation in
the database with row-level security, the RQ worker and beat scheduler run, and
`AUTH_MODE=oidc` puts Keycloak back in front of the app (realm `vantor`, client
`vantor-web`; the realm ships `admin` / `admin` for local work). Use this when
more than one tenant, background jobs, or a real identity provider matter.

### About sign-in

The client cannot manufacture a session in either mode. A token is issued by the
server, signed, carries a tenant and expires; one that is forged, signed by
another key, or missing a tenant is refused with a 401. What `AUTH_MODE=local`
relaxes is *who may ask for a session* — nothing else. The `DISABLE_AUTH=1`
escape hatch, which returned a full-Admin actor with no token at all in every
environment, has been removed, and `backend/tests/test_local_auth.py` fails if
it returns.


### 2. Launch the Backend API Service

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL="sqlite:///./_dev.db"
python -m uvicorn app.main:app --port 8000 --reload
```

`OIDC_ISSUER` and `JWT_AUDIENCE` have working defaults (`http://localhost:8080/realms/vantor`
and `vantor-web`) that match `.env.example`, so they are usually unnecessary. Set
`OIDC_ISSUER` only if your Keycloak is not on `http://localhost:8080` — it must be
byte-identical to the `iss` claim in the token, and `127.0.0.1` is a different
string from `localhost` even for the same server. A mismatch is not a crash: every
authenticated request answers `401 Invalid token` while `/health` stays green,
because `/health` touches no dependency.

To populate the dev database with realistic suppliers, contracts and notifications:

```powershell
$env:DATABASE_URL="sqlite:///./_dev.db"
python scripts/seed_enterprise_data.py
```

It seeds suppliers, contracts and notifications. RFQs, purchase orders, invoices and
budgets are left empty, so those panels show their empty state until you create
records through the API.

- API Documentation: `http://localhost:8000/docs` (Interactive OpenAPI Swagger, 90 operations across all 10 modules).
- Health & Readiness: `http://localhost:8000/healthz` and `http://localhost:8000/ready`.

### 3. Containerized Enterprise Deployment (Optional Docker Compose)

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

See `docs/08-deployment/local.md` for full environment variable configurations.

## Repository layout

```
README.md  LICENSE  SECURITY.md  CONTRIBUTING.md  CODE_OF_CONDUCT.md  CHANGELOG.md
.env.example  docker-compose.yml  .gitignore  mkdocs.yml
docs/
  BRAIN.md  README.md  glossary.md
  00-plan/{ROADMAP.md,REPOSITORY_AUDIT.md,MIGRATION_PLAN.md,masterdoc.md,SESSION.md}
  01-product/{requirements.md,portfolio.md}
  02-architecture/{system.md,domain.md,database.md,api.md}
  03-ai/{architecture.md,safety.md,evaluation.md}
  04-security/{architecture.md,threat-model.md}
  05-frontend/design-system.md
  06-brand/logo.md
  07-android/strategy.md
  08-deployment/local.md
  09-operations/runbook.md
  10-decisions/{README.md,ADR-001…007.md}
  11-specs-06-10/            (vendored Products 06–10 build-brain, read-only)
assets/brand/{vantor-logo-source.png,logo.svg,logo-mono.svg,logo-dark.svg,favicon.svg,app-icon.svg,social-preview.svg}
backend/  frontend/  worker/  api/  scripts/
(android/ arrives with the Coming-Soon native wave — strategy: docs/07-android/strategy.md)
mkdocs.yml  .github/{workflows/ci.yml,dependabot.yml}
```

## Documentation map

| Doc | Purpose |
|---|---|
| `docs/01-product/portfolio.md` | **The 10 products** — canonical list, per-product module + status |
| `docs/00-plan/REPOSITORY_AUDIT.md` | Audit of the 5 private repos behind products 01–05 (VERIFIED) |
| `docs/00-plan/MIGRATION_PLAN.md` | KEEP/ADAPT/MERGE/REFACTOR/REWRITE plan |
| `docs/00-plan/ROADMAP.md` | Phases 0–11, Definition of Done |
| `docs/01-product/requirements.md` | PRD |
| `docs/11-specs-06-10/README.md` | Vendored specs for products 06–10 (read-only input) |
| `docs/02-architecture/system.md` | Modular monolith, free stack |
| `docs/03-ai/architecture.md` | Gateway, typed tools, HITL, free providers |
| `docs/04-security/architecture.md` | Auth, tenancy, RBAC, audit |
| `docs/05-frontend/design-system.md` | Vantor UI system |
| `docs/07-android/strategy.md` | API-first mobile plan |

## Security

See `SECURITY.md`. Never commit secrets. Report vulnerabilities privately.

Enforced today, not planned: Keycloak OIDC with tenant and role claims from the
token, Postgres row-level security on every tenant table (fail-closed — no tenant
context, no rows), hash-chained audit log, idempotency keys, rate limiting, and
security headers on **both** the API and the web app. A Content-Security-Policy
delivered by the API governs documents the API serves, so the pages a user reads
are governed by a separate policy in `frontend/next.config.mjs`; `X-Frame-Options`,
`Referrer-Policy` and `Permissions-Policy` are set on the app's own responses too.

The worker authenticates with client credentials under a dedicated
`Service Identity` realm role, not an administrative one. It holds exactly the two
operations it performs — the contract expiry roll and the webhook drain — and
nothing else, so a leaked worker secret is not an administrative token. Machine
roles are deliberately not subsets of human roles, which is what makes that
checkable.

## Contributing

See `CONTRIBUTING.md` + `CODE_OF_CONDUCT.md`.

CI runs **weekly on Mondays 05:17 UTC, on manual dispatch, and on every push to
`main`**. On a push it runs the fast per-commit gates (lint, typecheck, vitest,
pytest, migration chain, OpenAPI drift, dependency audits, docs counts, secret and
encoding guards); the long weekly job adds the PG migration chain and the heavier
suites. Run the same gates locally before you push:

```powershell
python -m pytest backend/tests -q     # 330 tests (5 need PostgreSQL)
python scripts/verify_brain_links.py  # docs brain-link gate
cd frontend; npm run typecheck; npm run lint; npm run build
```

CI gates: secret guard, compose/env validation, required-docs presence, brain links,
`pytest`, Alembic upgrade/check/downgrade on real Postgres, OpenAPI drift
(`git diff --exit-code api/openapi.json`), frontend typecheck + lint + build, container
build, `pip-audit --strict`, `npm audit --audit-level=high`.

## License

**Apache-2.0** © 2026 Digi Tracks — see `LICENSE`. Free to use, self-host, modify,
and redistribute, including in closed-source or commercial products — no
copyleft obligation on your modifications, and no fee. Keep the copyright and
license notice; that's the only condition.

## Enquiries

Product: **VANTOR** by **Digi Tracks**. Email: **digi.tracks@outlook.com**.

## Roadmap summary

Phase 0 Discovery (audit) → 1 Architecture → 2 Design → 3 Foundation → 4 Core P2P → 5 Intelligence → 6 AI → 7 Premium UI → 8 Integrations → 9 Android → 10 Production hardening → 11 Portfolio extension (products 06–10). Details in `docs/00-plan/ROADMAP.md`.

> **Android app — Coming Soon (API-ready).** The `/api/v1` backend is already built
> for it (OIDC + RLS + approvals); the native Kotlin app starts as its own wave
> once device testing is available. See `docs/07-android/strategy.md`.
