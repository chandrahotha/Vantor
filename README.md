<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# VANTOR — Intelligent Procurement Operating System

🚀 **Live demo:** [vantor-os.vercel.app](https://vantor-os.vercel.app/)

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

> **Value. Intelligence. Control.** Built by **Digi Tracks** — enquiries: **digi.tracks@outlook.com**.

VANTOR is a unified, self-hostable procurement operating system: ten procurement
products in one coherent platform, from supplier risk to RFQs, contracts,
purchase orders, invoices, spend analytics, and an evidence-cited AI copilot.

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

Per-product detail: [`docs/01-product/portfolio.md`](docs/01-product/portfolio.md)
(the canonical list). One platform covers the full cycle — discovery,
onboarding, scorecards, risk, RFI/RFQ/RFP, quotations, awards, contracts,
requisitions, purchase orders, receipts, invoices, spend, savings, approvals,
documents, AI copilot, and integrations — every activity backed by evidence and audit.

**Status.** Backend: 386 pytest collected (377 passing, 9 skipped — the
PostgreSQL tier needs `PG_TEST_DATABASE_URL`), 98 API operations across 84
paths. Web: 166 vitest green across 13 suites, 15 page routes. Worker: 38 tests
collected (34 passing, 4 skipped — the 4 need a live Redis).

> Re-verified 2026-10-08 — backend `377 passed, 9 skipped`, worker
> `34 passed, 4 skipped`, frontend `166 passed`, OpenAPI drift check clean.
> Reproduce with `make verify`.

Not `PRODUCTION READY`. Know before you deploy:

- The default SQLite run does **not** exercise row-level security, composite
  foreign keys, or the pgvector index — those need a real Postgres
  (`PG_TEST_DATABASE_URL`). Tenant isolation on SQLite rests on the
  application layer alone (see `backend/README.md`).

## Why VANTOR

Procurement teams juggle suppliers, RFQs, quotes, contracts, POs, invoices,
spend, risk, and savings across disconnected tools. VANTOR connects them in one
**Procurement Graph**:

```
SUPPLIERS → SOURCING → RFQs → QUOTES → NEGOTIATION → CONTRACTS → PURCHASES → INVOICES → SPEND → PERFORMANCE → RISK → SAVINGS
```

with human + AI collaboration on top — every AI answer cites evidence,
confidence, and human-review gates.

## Features

- **Backend API** (FastAPI, 98 operations, 386 pytest collected): suppliers,
  scorecards, onboarding, RFQ→quote→award with optimizer, contracts with
  obligations/e-sign/11-dim matching, requisition→PO→receipt→invoice with
  3-way match, tiered approvals with SoD, budgets, spend ledger and
  intelligence, should-cost, catalogs, document pipeline
  (pgvector HNSW on Postgres, honest mode label elsewhere), notifications,
  AI gateway with typed tools + HITL + negotiation sim, webhooks.
- **Auth** (`local` or `oidc`, one verification path): `local` (default) needs
  no identity service — passwordless sessions for single-operator use, never
  exposed to untrusted networks. `oidc` uses Keycloak. Forged tokens are 401
  in both modes. Postgres RLS, RBAC, hash-chained audit, idempotency, rate
  limits, and security headers included.
- **Web app** (Next.js 16 / React 19, 15 routes): dashboard, supplier 360,
  requisitions, RFQs with comparison and award, contracts, orders with price
  check, spend analytics, documents, governance, integrations, negosim,
  notifications, evidence-grounded copilot, command palette (`Ctrl+K`), dark theme.
- **Worker + CI**: RQ + Redis with beat scheduler; per-push/PR lint,
  typecheck, tests, and builds, plus OpenAPI drift, migration-chain, and audit
  checks; weekly schedule and on-demand Postgres + Playwright tier.
- **Not yet**: provider OCR, full Phase-11 vendor acceptance matrices, realtime
  push (notifications poll), Android app (strategy only — API-ready).

Phase 10 hardening is `IN DEVELOPMENT`; Phase 9 Android is `PLANNED`.
Details: `docs/00-plan/ROADMAP.md`.

## Quickstart

### One container (SQLite, no identity service)

```bash
docker build -t vantor .
docker run -p 8080:8080 -v vantor-data:/data vantor
```

Open **http://localhost:8080** → **Log in to VANTOR** (no password — anyone
who can reach the URL is the operator; local/single-operator use only).
The volume persists the database, uploads, and session key. SQLite means
single-tenant only (no RLS) and no worker/scheduler.

### Backend + web separately (development)

```powershell
# API (SQLite file, schema created on first boot)
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

Open **http://localhost:3000**. API reference: `http://localhost:8000/api/docs`.
Health: `/api/v1/health` and `/api/v1/ready`.

`OIDC_ISSUER` defaults to `http://localhost:8080/realms/vantor` — override it
only if Keycloak lives elsewhere. It must match the token's `iss` claim
byte-for-byte (`127.0.0.1` ≠ `localhost`); a mismatch returns 401 on every
authenticated request while health stays green.

### Full stack (Postgres, Redis, worker, Keycloak)

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

Multi-tenant RLS, background jobs, and Keycloak OIDC (`AUTH_MODE=oidc`).
Full variable reference: `docs/08-deployment/local.md`.

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
  12-legal/ (drafts — not legally reviewed, see docs/12-legal/README.md)
assets/brand/{vantor-logo-source.png,logo.svg,logo-mono.svg,logo-dark.svg,favicon.svg,app-icon.svg,social-preview.svg}
backend/  frontend/  worker/  android/ (strategy only)  api/  scripts/  deploy/
.github/{workflows/{ci.yml,release.yml},dependabot.yml,ISSUE_TEMPLATE/,PULL_REQUEST_TEMPLATE.md}
```

| Doc | Purpose |
|---|---|
| `docs/01-product/portfolio.md` | The 10 products — canonical list |
| `docs/00-plan/ROADMAP.md` | Build phases, status, Definition of Done |
| `docs/02-architecture/system.md` | Modular monolith, free stack |
| `docs/03-ai/architecture.md` | Gateway, typed tools, HITL |
| `docs/04-security/architecture.md` | Auth, tenancy, RBAC, audit |
| `docs/05-frontend/design-system.md` | UI system |
| `docs/08-deployment/local.md` | Deployment reference |
| `docs/09-operations/runbook.md` | Health, backup, incidents |

## Security

See `SECURITY.md`. Never commit secrets; report vulnerabilities privately
(no public issues). Enforced: Keycloak OIDC, Postgres RLS (fail-closed),
hash-chained audit, idempotency, rate limiting, and security headers on both
API and web app. The worker holds a least-privilege `Service Identity` role
covering exactly its two jobs.

## Testing

```bash
make verify  # all 16 gates (or scripts/verify_all.ps1 / .sh)
```

```powershell
# Backend fast tier (SQLite, 386 collected — 377 pass, 9 need PG)
$env:APP_ENV="test"; $env:DATABASE_URL="sqlite://"
python -m pytest backend/tests -q
cd backend; ruff check app tests alembic; mypy app; cd ..
python -m pytest worker/tests -q
cd frontend; npm run typecheck; npm run lint; npm test; npm run build; cd ..
```

## Troubleshooting

- **Keycloak auth fails after `.env` reset**: the bootstrap password only
  applies to an empty database — `docker compose down -v; docker compose up -d`.
- **Uploads fail with `DOC_STORAGE_UNAVAILABLE`**: `S3_ENDPOINT` is
  unreachable — leave the `S3_*` vars blank for local-disk storage (`uploads/`).
- **Postgres permission denied**: app role (`vantor_app`) vs schema owner
  (`POSTGRES_USER`) — keep `APP_DB_PASSWORD` in sync (migration `0026`).
- **No Keycloak?** Set `AUTH_MODE=local` — the API issues its own sessions.

## Contributing

See `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`. CI runs on every push/PR to
`main`, weekly on Mondays 05:17 UTC, and on manual dispatch. The heavy tier
(Postgres, Alembic drills, Playwright E2E) runs only with `full_suite: true`.

## License

**Apache-2.0** © 2026 Digi Tracks — see `LICENSE`. Free to use, self-host,
modify, and redistribute, including commercially. Keep the copyright and
license notice.

## Enquiries

Product: **VANTOR** by **Digi Tracks** — **digi.tracks@outlook.com**.
Bugs/features: [GitHub Issues](../../issues) (steps, expected vs actual,
deployment mode). Vulnerabilities: `SECURITY.md` (private disclosure only).

## Roadmap

Architecture → Foundation → Core P2P → Intelligence → AI → Web UI →
Integrations → Android → Production hardening → Portfolio extension.
Status and Definition of Done: `docs/00-plan/ROADMAP.md`.

> **Android — coming soon (API-ready).** `/api/v1` already serves it
> (OIDC + RLS + approvals); the Kotlin app starts once device testing is
> available. See `docs/07-android/strategy.md`.
