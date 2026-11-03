# VANTOR — Intelligent Procurement Operating System

[![Live Demo: Vercel](https://img.shields.io/badge/demo-vantor--os.vercel.app-black.svg?logo=vercel)](https://vantor-os.vercel.app/)
[![CI: on push and PR](https://img.shields.io/badge/CI-push%20%2B%20PR-brightgreen.svg)](.github/workflows/ci.yml)
[![Tests: 386 backend + 166 frontend](https://img.shields.io/badge/tests-386%20backend%20%2B%20166%20frontend-brightgreen.svg)](backend/tests/)
[![API: 98 operations](https://img.shields.io/badge/API-98%20operations-blue.svg)](api/openapi.json)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Backend: FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)](backend/)
[![Frontend: Next.js](https://img.shields.io/badge/frontend-Next.js-black.svg)](frontend/)
[![Auth: local or OIDC](https://img.shields.io/badge/auth-local%20or%20OIDC-orange.svg)](docs/04-security/architecture.md)
[![DB: Postgres RLS](https://img.shields.io/badge/db-Postgres%20RLS-336791.svg)](docs/02-architecture/database.md)

> **Value. Intelligence. Control.**

VANTOR is a self-hostable procurement operating system. It puts suppliers,
sourcing, contracts, purchase orders, invoices, spend analytics, budgets,
approvals and an evidence-cited AI copilot behind one coherent system — with
one audit trail and one permission model across all of it.

**Live demo:** [vantor-os.vercel.app](https://vantor-os.vercel.app/) ·
Enquiries: **digi.tracks@outlook.com**

## What VANTOR does

Procurement teams juggle the same data across disconnected tools. VANTOR
connects it into one graph:

```
SUPPLIERS → SOURCING → RFQs → QUOTES → NEGOTIATION → CONTRACTS → PURCHASES → INVOICES → SPEND → PERFORMANCE → RISK → SAVINGS
```

with human and AI collaboration on top: every AI answer carries its evidence,
its confidence, and a human-review gate.

| Area | What it does |
|---|---|
| **Supplier management** | Supplier records, risk scorecards, qualification workflow, onboarding with segregation-of-duties decisions |
| **Sourcing & RFQs** | RFQ → quote → award, multi-quote comparison, share-capped allocation optimizer |
| **Contracts** | Obligations, renewal windows, e-signature handover, contract-to-PO-to-invoice matching across eleven dimensions |
| **Purchase orders** | Requisition → PO → receipt → invoice chain, tiered approvals, budget enforcement, 3-way match |
| **Invoices** | Invoice intake, approval routing, variance handling against the PO and receipt |
| **Spend intelligence** | Spend cube by category/supplier/BU, leakage, maverick spend, supplier concentration |
| **Should-cost & price intelligence** | Should-cost modelling, median price baselines, price-anomaly cases |
| **Budgets & approvals** | Budget pools, configurable unset-policy, quorum approvals, separation of duties |
| **Documents & evidence** | Upload → validate → store → extract → chunk, keyword and vector search, audit trail |
| **AI copilot & negotiation simulator** | Typed tool registry, evidence-framed answers, human-in-the-loop approvals, concession ladder with a walk-away floor |

## Architecture

A modular monolith with a separate worker and web app — one deployment
topology, one permission model, no distributed-system tax.

| Component | Stack | Role |
|---|---|---|
| **API** | Python 3.14, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | `/api/v1` — 98 API operations across 84 paths |
| **Database** | PostgreSQL + pgvector | Primary store, row-level security, vector index |
| **Web app** | Node 22, Next.js 16 (App Router), React 19, TypeScript 6 | 15 page routes |
| **Worker** | Python, RQ, Redis | Scheduled jobs: expiry roll, spend snapshots, webhook drain |
| **Identity** | Keycloak (OIDC) or built-in local auth | One verification path, two modes |
| **AI gateway** | Pluggable providers, BYO key | Typed tools, evidence contracts, human review; `disabled` by default |

**Auth modes.** `local` (the default) needs no identity service — passwordless
sessions for single-operator use, never exposed to untrusted networks. `oidc`
uses Keycloak. Forged tokens are rejected in both modes.

## Quickstart

### One container (SQLite, no identity service)

```bash
docker build -t vantor .
docker run -p 8080:8080 -v vantor-data:/data vantor
```

Open **http://localhost:8080** and sign in — no password. The volume persists
the database, uploads and session key. SQLite means single-tenant only (no
RLS) and no worker or scheduler.

### Backend + web separately (development)

```bash
# API (SQLite file, schema created on first boot)
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
DATABASE_URL="sqlite:///./data/vantor.db" .venv/bin/python -m uvicorn app.main:app --port 8000
```

```bash
# Web
cd frontend
npm ci
NEXT_PUBLIC_API_URL="http://localhost:8000" npm run dev
```

Open **http://localhost:3000**. API reference: `http://localhost:8000/api/docs`.
Health: `/api/v1/health` and `/api/v1/ready`.

`OIDC_ISSUER` defaults to `http://localhost:8080/realms/vantor` — override it
only if Keycloak lives elsewhere. It must match the token's `iss` claim
byte-for-byte (`127.0.0.1` ≠ `localhost`); a mismatch returns 401 on every
authenticated request while health stays green.

### Full stack (Postgres, Redis, worker, Keycloak)

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

Multi-tenant RLS, background jobs, and Keycloak OIDC (`AUTH_MODE=oidc`).
Every environment variable is listed with a default in `.env.example`.

## API

The contract is generated from the code and committed at `api/openapi.json`.
CI regenerates it and fails the build if it drifts, so the file in the
repository is always the contract the server actually serves.

- **98 API operations across 84 paths**, versioned under `/api/v1`.
- Idempotency keys on mutating workflow actions; cursor pagination with
  filter, sort and field selection.
- A single response envelope — `{data, pagination, error, requestId}` — and
  typed validation errors with field paths.

## Security

See [`SECURITY.md`](SECURITY.md). Never commit secrets; report
vulnerabilities privately, not as a public issue.

Enforced in the code, not just documented: Keycloak OIDC, PostgreSQL
row-level security that fails closed, role-based access control, a
hash-chained audit log, idempotent mutations, rate limiting, and security
headers on both the API and the web app. The worker holds a least-privilege
service role covering exactly its two jobs, and it is deliberately not a
subset of any human role.

## Testing

```bash
make verify    # the full gate set
```

```bash
# Backend fast tier (SQLite — 386 collected, 377 pass, 9 need Postgres)
APP_ENV=test DATABASE_URL=sqlite:// python -m pytest backend/tests -q

# Worker
python -m pytest worker/tests -q

# Web
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
```

Current state: **386 pytest collected** on the backend, **166 vitest green**
across 13 suites in the web app, and 38 worker tests collected. The gates also
cover lint, type checking, dependency audits, an OpenAPI drift check, a
migration-chain check and a secret scan.

## Current limitations

Know these before you deploy.

- **Not production-hardened.** There is no SLA, no on-call rotation and no
  upgrade path. Treat it as a capable reference implementation you own.
- **The SQLite tier does not exercise the database.** Row-level security,
  composite foreign keys and the pgvector index need a real PostgreSQL
  (`PG_TEST_DATABASE_URL`). On SQLite, tenant isolation rests on the
  application layer alone.
- **Document OCR is absent.** Upload, validation, storage, extraction,
  chunking and audit are real; a scanned PDF with no text layer is
  quarantined, not OCR'd.
- **Search is lexical, not semantic.** Vectors are stored and compared for
  real, but a cosine over bag-of-words vectors is lexical. The API labels
  the mode honestly in its response rather than claiming "semantic search".
  With no embedding provider configured, search is keyword-only.
- **Notifications poll.** There is no realtime push.
- **The worker drains one tenant.** Its delivery loop goes through the
  tenant-scoped HTTP route, so a single worker will not deliver other
  tenants' webhooks. Cross-tenant draining needs its own explicitly
  cross-tenant identity.
- **No Android client yet.** The API is ready for one; the app is not built.

## Documentation

The full documentation index is [`docs/README.md`](docs/README.md) —
architecture, security model, deployment, operations, ADRs and the design
system, each written to be read on its own.

| Start here | What it covers |
|---|---|
| [`docs/02-architecture/system.md`](docs/02-architecture/system.md) | How the pieces fit together |
| [`docs/02-architecture/database.md`](docs/02-architecture/database.md) | Schema, tenancy, row-level security |
| [`docs/04-security/architecture.md`](docs/04-security/architecture.md) | Auth, RBAC, audit |
| [`docs/08-deployment/local.md`](docs/08-deployment/local.md) | Every environment variable |
| [`docs/09-operations/runbook.md`](docs/09-operations/runbook.md) | Health, backup, incidents |

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). CI runs on every push and pull
request to `main`, weekly on Mondays, and on manual dispatch. A heavier tier
(Postgres, migration drills, Playwright end-to-end) runs on demand with
`full_suite: true`.

## License

**Apache-2.0** © 2026 Digi Tracks — see [`LICENSE`](LICENSE). Free to use,
self-host, modify and redistribute, including commercially. Keep the copyright
and license notice.

## Contact

- **Product:** VANTOR by Digi Tracks — **digi.tracks@outlook.com**
- **Bugs and features:** [GitHub Issues](../../issues) — please include steps,
  expected vs actual behaviour, and your deployment mode.
- **Vulnerabilities:** [`SECURITY.md`](SECURITY.md) — private disclosure only.

## Changelog

[`CHANGELOG.md`](CHANGELOG.md)
