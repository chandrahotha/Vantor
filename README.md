<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# VANTOR — Intelligent Procurement Operating System

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Backend: FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)](backend/)
[![Frontend: Next.js](https://img.shields.io/badge/frontend-Next.js-black.svg)](frontend/)
[![Auth: Keycloak OIDC](https://img.shields.io/badge/auth-Keycloak%20OIDC-orange.svg)](docs/04-security/architecture.md)
[![DB: Postgres RLS](https://img.shields.io/badge/db-Postgres%20RLS-336791.svg)](docs/02-architecture/database.md)
[![Tests: 82 passing](https://img.shields.io/badge/tests-82%20passing-brightgreen.svg)](backend/tests/)
[![CI: weekly](https://img.shields.io/badge/CI-weekly-yellow.svg)](.github/workflows/ci.yml)
[![Docs: brain-linked](https://img.shields.io/badge/docs-brain--linked-6c47ff.svg)](docs/BRAIN.md)

> **Value. Intelligence. Control.**
> Built by **Digi Tracks**. For enquiries: **digi.tracks@outlook.com**.

VANTOR is a unified, production-grade procurement operating system merging five procurement products into one coherent platform:

- Supplier intelligence (ex-SupplierRadar/Valtrix)
- Contract intelligence (ex-ContractGuard/Veridox)
- Cost intelligence (ex-CostPilot/Costryn)
- Sourcing / RFQ intelligence (ex-RFQLens/QuotientX)
- Procurement AI agent (ex-ProcurementOS-Agent)

> **One-stop procurement:** supplier discovery, onboarding, scorecards, risk, sourcing projects, RFI/RFQ/RFP, quotations, bid evaluation, awards, contracts, obligations, renewals, requisitions, purchase orders, goods receipt, invoices, spend analytics, savings tracking, approvals, workflows, documents, AI copilot, integrations, and mobile approvals — every activity cited with evidence and audit.

**Status: `TESTED` backend (82 pytest green) + working Next.js app — not yet `PRODUCTION READY` (see gate checklist in `docs/00-plan/ROADMAP.md` Phase 10).****

## Why VANTOR

Procurement teams juggle suppliers, RFQs, quotes, contracts, POs, invoices, spend, risk, and savings across disconnected tools. VANTOR connects them in one **Procurement Graph**:

```
SUPPLIERS → SOURCING → RFQs → QUOTES → NEGOTIATION → CONTRACTS → PURCHASES → INVOICES → SPEND → PERFORMANCE → RISK → SAVINGS
```

with `PROCUREMENT AI + HUMAN + AI COLLABORATION` on top — every AI answer cited with evidence, confidence, and human-review gates.

## What works today (tested, no mocks)

- [x] Backend API (FastAPI, 56 routes, 82 tests green): suppliers + scorecards + onboarding, RFQ→quote→award + optimizer, contracts + matching + e-sign, requisitions→PO→receipt→invoice with 3-way match, tiered approvals + SoD + budgets, spend ledger + intelligence + should-cost + price cases, documents, AI gateway + typed tools + nego sim, webhooks
- [x] AuthN/Z: Keycloak OIDC + RLS tenant isolation + RBAC + hash-chained audit + idempotency + rate limiting + security headers + honest `/ready`
- [x] Web app (Next.js 14, build green): dashboard, suppliers grid, RFQs + comparison, contracts, orders, spend, documents, copilot, command palette (`Ctrl+K`)
- [x] Worker (RQ + Redis), free-only local stack (`docker compose up`), weekly CI, operations runbook
- [ ] Document OCR/extract/embed, live-LLM streaming, notifications/realtime, Android (Coming Soon — API-ready)

Never claim functionality that is not implemented. Phase 0 audit `VERIFIED`, Phases 3–4 `TESTED`, 5–8 `IN DEVELOPMENT` (see `docs/00-plan/ROADMAP.md`).

## Quickstart (local, 100% free)

Prerequisites: Docker + Docker Compose, Node 20+, Python 3.11+ (for worker later), Git.

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

See `docs/08-deployment/local.md` and `.env.example`.

## Repository layout

```
README.md  LICENSE  SECURITY.md  CONTRIBUTING.md  CODE_OF_CONDUCT.md  CHANGELOG.md
.env.example  docker-compose.yml  .gitignore  mkdocs.yml
docs/
  BRAIN.md  README.md  glossary.md
  00-plan/{ROADMAP.md,REPOSITORY_AUDIT.md,MIGRATION_PLAN.md,masterdoc.md}
  01-product/requirements.md
  02-architecture/{system.md,domain.md,database.md,api.md}
  03-ai/{architecture.md,safety.md,evaluation.md}
  04-security/{architecture.md,threat-model.md}
  05-frontend/design-system.md
  06-brand/logo.md
  07-android/strategy.md
  08-deployment/local.md
  09-operations/runbook.md
  10-decisions/{README.md,ADR-001…006.md}
assets/brand/{vantor-logo-source.png,logo.svg,logo-mono.svg,logo-dark.svg,favicon.svg,app-icon.svg,social-preview.svg}
backend/  frontend/  worker/  api/  scripts/
(android/ arrives with the Coming-Soon native wave — strategy: docs/07-android/strategy.md)
mkdocs.yml  .github/workflows/ci.yml
```

## Documentation map

| Doc | Purpose |
|---|---|
| `docs/00-plan/REPOSITORY_AUDIT.md` | Audit of 5 private repos (blocked until access) |
| `docs/00-plan/MIGRATION_PLAN.md` | KEEP/ADAPT/MERGE/REFACTOR/REWRITE plan |
| `docs/00-plan/ROADMAP.md` | Phases 0–10, Definition of Done |
| `docs/01-product/requirements.md` | PRD |
| `docs/02-architecture/system.md` | Modular monolith, free stack |
| `docs/03-ai/architecture.md` | Gateway, typed tools, HITL, free providers |
| `docs/04-security/architecture.md` | Auth, tenancy, RBAC, audit |
| `docs/05-frontend/design-system.md` | Vantor UI system |
| `docs/07-android/strategy.md` | API-first mobile plan |

## Security

See `SECURITY.md`. Never commit secrets. Report vulnerabilities privately. Keycloak OIDC + MFA planned; RLS tenant isolation mandatory.

## Contributing

See `CONTRIBUTING.md` + `CODE_OF_CONDUCT.md`. CI runs format/lint/typecheck/tests/security scans on every PR.

## License

**AGPL-3.0-or-later** © 2026 Digi Tracks — see `LICENSE`. Free to use, self-host,
and modify; network-service distribution of modified versions must publish source
(§13). Commercial exceptions: digi.tracks@outlook.com.

## Enquiries

Product: **VANTOR** by **Digi Tracks**. Email: **digi.tracks@outlook.com**.

## Roadmap summary

Phase 0 Discovery (audit) → 1 Architecture → 2 Design → 3 Foundation → 4 Core P2P → 5 Intelligence → 6 AI → 7 Premium UI → 8 Integrations → 9 Android → 10 Production hardening. Details in `docs/00-plan/ROADMAP.md`.

> **Android app — Coming Soon (API-ready).** The `/api/v1` backend is already built
> for it (OIDC + RLS + approvals); the native Kotlin app starts as its own wave
> once device testing is available. See `docs/07-android/strategy.md`.
