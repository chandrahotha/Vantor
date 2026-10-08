<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# VANTOR - Intelligent Procurement Operating System

🚀 **Live Interactive Demo:** [VANTOR - Intelligent Procurement Operating System](https://vantor-os.vercel.app/)

[![Live Demo: Vercel](https://img.shields.io/badge/demo-vantor--os.vercel.app-black.svg?logo=vercel)](https://vantor-os.vercel.app/)
[![CI: on push and PR](https://img.shields.io/badge/CI-push%20%2B%20PR-brightgreen.svg)](.github/workflows/ci.yml)
[![Tests: 386 backend + 166 frontend](https://img.shields.io/badge/tests-386%20backend%20%2B%20166%20frontend-brightgreen.svg)](backend/tests/)
[![API: 98 operations](https://img.shields.io/badge/API-98%20operations-blue.svg)](api/openapi.json)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Backend: FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)](backend/)
[![Frontend: Next.js](https://img.shields.io/badge/frontend-Next.js-black.svg)](frontend/)
[![Auth: local or OIDC](https://img.shields.io/badge/auth-local%20or%20OIDC-orange.svg)](docs/04-security/architecture.md)
[![DB: Postgres RLS](https://img.shields.io/badge/db-Postgres%20RLS-336791.svg)](docs/02-architecture/database.md)
[![Docs: brain-linked](https://img.shields.io/badge/docs-brain--linked-6c47ff.svg)](docs/BRAIN.md)

> **Value. Intelligence. Control.**
> Built by **Digi Tracks**. For enquiries: **digi.tracks@outlook.com**.
> Explore live on Vercel: **[VANTOR - Intelligent Procurement Operating System](https://vantor-os.vercel.app/)**.

VANTOR is a unified, production-grade procurement operating system merging **ten** procurement products into one coherent platform.

| # | Product | VANTOR module | Status |
|---|---|---|---|
| 01 | ProcurementOS Agent | AI gateway + typed tool registry + HITL approvals | `TESTED` |
| 02 | RFQLens - RFQ → sourcing decision | `sourcing/` RFQ→quote→award + split optimizer | `TESTED` |
| 03 | CostPilot - should-cost + negotiation intelligence | `spend/` should-cost engine + price intel | `TESTED` |
| 04 | ContractGuard - contract → PO → invoice compliance | `contracts/` + 11-dim matching + e-sign | `TESTED` |
| 05 | SupplierRadar - supplier risk intelligence | `suppliers/` + scorecards + qualification | `TESTED` |
| 06 | Strategic Sourcing Optimization | `sourcing/` optimizer (share-capped allocation) | `TESTED` |
| 07 | Procurement Spend Intelligence | `spend/` cube, leakage, maverick, concentration | `TESTED` |
| 08 | Supplier Onboarding & Qualification | `suppliers/` certs→scorecard→SoD decision | `TESTED` |
| 09 | PO Price Intelligence | `spend/` median baseline + anomaly cases | `TESTED` |
| 10 | AI Supplier Negotiation Simulator | `ai/` concession ladder + walk-away floor | `TESTED` |

Canonical list with per-product detail: **[`docs/01-product/portfolio.md`](docs/01-product/portfolio.md)**.

> Products 01–05 cover the supplier, sourcing, cost, contract, and spend
> foundations; products 06–10 extend them as native modules (optimizer, spend
> intelligence, onboarding, price intel, negotiation simulator) - see
> [`docs/01-product/portfolio.md`](docs/01-product/portfolio.md) for the canonical mapping.

> **One-stop procurement:** supplier discovery, onboarding, scorecards, risk, sourcing projects, RFI/RFQ/RFP, quotations, bid evaluation, awards, contracts, obligations, renewals, requisitions, purchase orders, goods receipt, invoices, spend analytics, savings tracking, approvals, workflows, documents, AI copilot, and integrations - every activity cited with evidence and audit.

**Status.** Backend: 386 pytest collected (377 passing, 9 skipped — the PostgreSQL
tier, which needs `PG_TEST_DATABASE_URL`), 98 API operations across 84 paths.
Web: 166 vitest green across 13 suites, 15 page routes. Worker: 38 tests
collected (34 passing, 4 skipped — the 4 need a live Redis).

Not `PRODUCTION READY`, and two qualifications matter more than the counts:

- The suite is honest about what it does not cover. Row-level security, the
  composite foreign keys, and the pgvector index are only exercised when
  `PG_TEST_DATABASE_URL` points at a real Postgres — the default SQLite run
  does not cover them (see `backend/README.md`).
- Tenant isolation on SQLite rests on the application layer alone. The
  multi-tenant guarantees (RLS, least-privilege `vantor_app` role) are a
  Postgres property, proven by the `pg`-marked tests and the Alembic chain,
  not by the default run.

## Why VANTOR

Procurement teams juggle suppliers, RFQs, quotes, contracts, POs, invoices, spend, risk, and savings across disconnected tools. VANTOR connects them in one **Procurement Graph**:

```
SUPPLIERS → SOURCING → RFQs → QUOTES → NEGOTIATION → CONTRACTS → PURCHASES → INVOICES → SPEND → PERFORMANCE → RISK → SAVINGS
```

with human + AI collaboration on top - every AI answer cited with evidence, confidence, and human-review gates.

## What works today (tested, no mocks)

- [x] Backend API (FastAPI, 98 operations across 84 paths, 386 pytest collected): suppliers + scorecards + onboarding + qualification decide, RFQ→quote→award + share-capped optimizer, contracts + obligations + e-sign + matching, requisitions→PO→receipt→invoice with 3-way match, tiered approvals + SoD + budgets, spend ledger + intelligence + should-cost + price cases (per-currency), catalogs, documents + extraction/embeddings/search (native pgvector HNSW index on Postgres, keyword prefilter elsewhere, honest mode label), notifications (per-recipient read, real polling), AI gateway + typed tools + HITL + negotiation sim, webhooks
- [x] AuthN/Z: two modes, same verification path. **`AUTH_MODE=local` (default)** makes the API its own issuer - it holds an RSA keypair and mints RS256 tokens, so the product runs with no identity service at all. It is **passwordless**: `POST /api/v1/auth/session` issues a session to whoever asks, which means *anyone who can reach the deployment is the operator*. That is the deliberate trade for a one-container deploy; do not expose such a deployment to an untrusted network. **`AUTH_MODE=oidc`** requires Keycloak as before. In both modes the token is signed, carries a tenant, expires, and is verified identically - a forged or foreign-signed token is a 401, which `tests/test_local_auth.py` asserts. Plus RLS tenant isolation (Postgres only), RBAC, hash-chained audit, idempotency, rate limiting, security headers and an honest `/ready`. The `DISABLE_AUTH=1` escape hatch - which returned a full-Admin actor with no token, in every environment, under a docstring saying no such branch existed - has been removed.
- [x] Web app (Next.js 16 / React 19, 15 routes): dashboard, suppliers grid + supplier 360, requisitions, RFQs + comparison + award, contracts, orders (+ PO price check + optimizer trigger), spend (cube/leakage/maverick/should-cost + cases), documents, governance (audit chain + catalog + budgets), integrations, negosim, notifications, copilot (tool-grounded with evidence), command palette (`Ctrl+K`), dark theme, error/loading/not-found boundaries
- [x] Worker (RQ + Redis + beat scheduler), free-only local stack (`docker compose up`), CI: per-push and per-PR lint/typecheck/vitest/pytest on every commit plus a weekly schedule, Alembic PG migration chain + OpenAPI drift check + pip-audit + npm audit, load-test script (`backend/scripts/load_test.py`)
- [ ] Real-world providers live-checks: OCR engine not shipped, full Phase 11 vendor matrices not yet run, deeper HITL contract chain pending, realtime push (notifications poll), Android app (Phase 9, not started)

All 10 products `TESTED` on core paths. Phase 10 production hardening is
`IN DEVELOPMENT` (monitoring wired; restore drills and OTEL pending). Phase 9
Android is `PLANNED` (strategy only — no app code yet). `docs/00-plan/ROADMAP.md`
has the per-phase status and remaining work.

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
alone - single tenant only; and with no Redis there is no worker and no
scheduler, so nothing that depends on background execution runs.

### 1. Backend + web separately (development)

```powershell
# API - SQLite file, schema created on first boot
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

- API reference: `http://localhost:8000/api/docs` (interactive Swagger, 98 operations across all 10 modules).
- Health & readiness: `http://localhost:8000/api/v1/health` and `http://localhost:8000/api/v1/ready`.

`OIDC_ISSUER` and `JWT_AUDIENCE` default to `http://localhost:8080/realms/vantor`
and `vantor-web`, matching `.env.example` — set `OIDC_ISSUER` only if your
Keycloak lives elsewhere. It must be byte-identical to the token's `iss` claim
(`127.0.0.1` and `localhost` are different strings): a mismatch answers `401`
on every authenticated request while `/api/v1/health` stays green, because
health touches no dependency.

### 2. Full stack (Postgres, Redis, worker, Keycloak)

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

This is the multi-tenant configuration: Postgres enforces tenant isolation in
the database with row-level security, the RQ worker and beat scheduler run, and
`AUTH_MODE=oidc` puts Keycloak back in front of the app (realm `vantor`, client
`vantor-web`; bootstrap credentials come from `KEYCLOAK_ADMIN*` in `.env`).

See `docs/08-deployment/local.md` for the full environment reference.

### About sign-in

The client cannot manufacture a session in either mode. A token is issued by the
server, signed, carries a tenant and expires; one that is forged, signed by
another key, or missing a tenant is refused with a 401. What `AUTH_MODE=local`
relaxes is *who may ask for a session* - nothing else. The `DISABLE_AUTH=1`
escape hatch, which returned a full-Admin actor with no token at all in every
environment, has been removed, and `backend/tests/test_local_auth.py` fails if
it returns.

## Repository layout

```
README.md  LICENSE  SECURITY.md  CONTRIBUTING.md  CODE_OF_CONDUCT.md  CHANGELOG.md
.env.example  docker-compose.yml  Dockerfile  .gitignore  mkdocs.yml  Makefile
docs/
  BRAIN.md  README.md  glossary.md
  00-plan/ROADMAP.md
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
  12-legal/ (draft legal docs - not legally reviewed, see docs/12-legal/README.md)
assets/brand/{vantor-logo-source.png,logo.svg,logo-mono.svg,logo-dark.svg,favicon.svg,app-icon.svg,social-preview.svg}
backend/  frontend/  worker/  android/ (strategy only)  api/  scripts/  deploy/
.github/{workflows/{ci.yml,release.yml},dependabot.yml,ISSUE_TEMPLATE/,PULL_REQUEST_TEMPLATE.md}
```

## Documentation map

| Doc | Purpose |
|---|---|
| `docs/01-product/portfolio.md` | **The 10 products** - canonical list, per-product module + status |
| `docs/00-plan/ROADMAP.md` | Build phases, per-phase status, Definition of Done |
| `docs/01-product/requirements.md` | PRD |
| `docs/02-architecture/system.md` | Modular monolith, free stack |
| `docs/03-ai/architecture.md` | Gateway, typed tools, HITL, free providers |
| `docs/04-security/architecture.md` | Auth, tenancy, RBAC, audit |
| `docs/05-frontend/design-system.md` | Vantor UI system |
| `docs/07-android/strategy.md` | API-first mobile plan |
| `docs/08-deployment/local.md` | Local + compose deployment |
| `docs/09-operations/runbook.md` | Health, backup, incidents |

## Security

See `SECURITY.md`. Never commit secrets. Report vulnerabilities privately.

Enforced today, not planned: Keycloak OIDC with tenant and role claims from the
token, Postgres row-level security on every tenant table (fail-closed - no tenant
context, no rows), hash-chained audit log, idempotency keys, rate limiting, and
security headers on **both** the API and the web app. A Content-Security-Policy
delivered by the API governs documents the API serves, so the pages a user reads
are governed by a separate policy in `frontend/next.config.mjs`; `X-Frame-Options`,
`Referrer-Policy` and `Permissions-Policy` are set on the app's own responses too.

The worker authenticates with client credentials under a dedicated
`Service Identity` realm role, not an administrative one. It holds exactly the two
operations it performs - the contract expiry roll and the webhook drain - and
nothing else, so a leaked worker secret is not an administrative token. Machine
roles are deliberately not subsets of human roles, which is what makes that
checkable.

## Testing & Verification

A one-shot local verification suite is provided to exercise all 16 repository gates (secret scanning, encoding, brain links, migration linearity, image digests, palette contrast, doc counts, backend lint/mypy/pytest, worker lint/pytest, frontend tsc/eslint/vitest, and Next.js production build):

```bash
# Using Make (Linux / macOS)
make verify

# Or directly via script:
# Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1

# Linux / macOS Bash
bash scripts/verify_all.sh
```

To run individual verification tiers:
```powershell
# Backend fast tier (SQLite in-memory, 386 tests collected, 377 passing, 9 skipped for PG)
$env:APP_ENV="test"; $env:DATABASE_URL="sqlite://"
python -m pytest backend/tests -q

# Backend lint and type checking
cd backend; ruff check app tests alembic; mypy app; cd ..

# Worker unit tests
python -m pytest worker/tests -q

# Frontend checks
cd frontend; npm run typecheck; npm run lint; npm test; npm run build; cd ..
```

## Troubleshooting

### 1. Keycloak admin bootstrap fails on restarted volumes
If `keycloak-init` fails with an authentication error after resetting `.env`, Keycloak only sets `KC_BOOTSTRAP_ADMIN_PASSWORD` on an empty database. Existing volumes preserve the previous credentials. To reset Keycloak state cleanly:
```powershell
docker compose down -v
docker compose up -d
```

### 2. Document upload fails with 503 DOC_STORAGE_UNAVAILABLE
If `S3_ENDPOINT` points to an unreachable host (or a removed MinIO container), document upload will report `DOC_STORAGE_UNAVAILABLE`. To use local-disk storage, leave `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, and `S3_SECRET_KEY` blank in `.env`. Files will land in `UPLOAD_DIR` (`uploads/`).

### 3. Database connection fails with permission denied on Postgres
Migration `0026_app_role_least_privilege` separates the schema owner (`POSTGRES_USER`, superuser used only for migrations) from the restricted application role (`vantor_app`, used by `DATABASE_URL`). Ensure `APP_DB_PASSWORD` matches between `.env` and the migration environment so the application role can authenticate and respect Row Level Security.

### 4. Running without Keycloak in lightweight single-container mode
To run the API without Keycloak, set `AUTH_MODE=local`. The API becomes its own token issuer with local RSA keypairs, suitable for single-node development and quickstarts without standing up an identity container.

## Contributing

See `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.

CI runs automatically on every push and pull request to `main`, weekly on Mondays at 05:17 UTC, and on manual workflow dispatch (`workflow_dispatch`). The workflow enforces secret scanning, config validation, linting (Ruff), typechecking (Mypy + tsc), test suites (pytest + vitest), and Next.js production builds. The heavy tier (PostgreSQL service containers, Alembic migration drills, Playwright E2E) runs only via workflow dispatch with `full_suite: true`.

## License

**Apache-2.0** © 2026 Digi Tracks - see `LICENSE`. Free to use, self-host, modify,
and redistribute, including in closed-source or commercial products - no
copyleft obligation on your modifications, and no fee. Keep the copyright and
license notice; that's the only condition.

## Enquiries

Product: **VANTOR** by **Digi Tracks**. Email: **digi.tracks@outlook.com**.

Found a bug or want a feature? Please open a [GitHub Issue](../../issues) —
include steps to reproduce, expected vs actual behaviour, and your deployment
mode (`local` or `oidc`). For vulnerabilities, see `SECURITY.md` (private
disclosure only, never a public issue).

## Roadmap summary

Architecture → Design → Foundation → Core P2P → Intelligence → AI → Web UI →
Integrations → Android → Production hardening → Portfolio extension (products
06–10). Current phase status and the Definition of Done live in
`docs/00-plan/ROADMAP.md`.

> **Android app - Coming Soon (API-ready).** The `/api/v1` backend is already built
> for it (OIDC + RLS + approvals); the native Kotlin app starts as its own wave
> once device testing is available. See `docs/07-android/strategy.md`.
