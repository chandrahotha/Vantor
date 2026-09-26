<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# VANTOR — Intelligent Procurement Operating System

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Backend: FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)](backend/)
[![Frontend: Next.js](https://img.shields.io/badge/frontend-Next.js-black.svg)](frontend/)
[![Auth: Keycloak OIDC](https://img.shields.io/badge/auth-Keycloak%20OIDC-orange.svg)](docs/04-security/architecture.md)
[![DB: Postgres RLS](https://img.shields.io/badge/db-Postgres%20RLS-336791.svg)](docs/02-architecture/database.md)
[![Tests: 89 passing](https://img.shields.io/badge/tests-89%20passing-brightgreen.svg)](backend/tests/)
[![API: 75 operations](https://img.shields.io/badge/API-75%20operations-blue.svg)](api/openapi.json)
[![Deps: 0 known vulns](https://img.shields.io/badge/deps-0%20known%20vulns-brightgreen.svg)](.github/dependabot.yml)
[![CI: weekly](https://img.shields.io/badge/CI-weekly-yellow.svg)](.github/workflows/ci.yml)
[![Docs: brain-linked](https://img.shields.io/badge/docs-brain--linked-6c47ff.svg)](docs/BRAIN.md)

> **Value. Intelligence. Control.**
> Built by **Digi Tracks**. For enquiries: **digi.tracks@outlook.com**.

VANTOR is a unified, production-grade procurement operating system merging **ten** procurement products into one coherent platform.

| # | Product | VANTOR module | Status |
|---|---|---|---|
| 01 | ProcurementOS Agent | AI gateway + typed tool registry + HITL approvals | `IN DEVELOPMENT` |
| 02 | RFQLens — RFQ → sourcing decision | `sourcing/` RFQ→quote→award + split optimizer | `TESTED` |
| 03 | CostPilot — should-cost + negotiation intelligence | `spend/` should-cost engine + price intel | `TESTED` |
| 04 | ContractGuard — contract → PO → invoice compliance | `contracts/` + 11-dim matching + e-sign | `TESTED` |
| 05 | SupplierRadar — supplier risk intelligence | `suppliers/` + scorecards + qualification | `TESTED` |
| 06 | Strategic Sourcing Optimization | `sourcing/` optimizer (share-capped allocation) | `IN DEVELOPMENT` |
| 07 | Procurement Spend Intelligence | `spend/` cube, leakage, maverick, concentration | `IN DEVELOPMENT` |
| 08 | Supplier Onboarding & Qualification | `suppliers/` certs→scorecard→SoD decision | `IN DEVELOPMENT` |
| 09 | PO Price Intelligence | `spend/` median baseline + anomaly cases | `IN DEVELOPMENT` |
| 10 | AI Supplier Negotiation Simulator | `ai/` concession ladder + walk-away floor | `IN DEVELOPMENT` |

Canonical list with per-product detail: **[`docs/01-product/portfolio.md`](docs/01-product/portfolio.md)**.

> Products 01–05 came from the five private repositories audited in Phase 0
> ([`docs/00-plan/REPOSITORY_AUDIT.md`](docs/00-plan/REPOSITORY_AUDIT.md)). Products 06–10
> arrived later as a vendored build-brain
> ([`docs/11-specs-06-10/`](docs/11-specs-06-10/README.md)). "Five" in older docs refers to
> the **audit scope**, never the product count.

> **One-stop procurement:** supplier discovery, onboarding, scorecards, risk, sourcing projects, RFI/RFQ/RFP, quotations, bid evaluation, awards, contracts, obligations, renewals, requisitions, purchase orders, goods receipt, invoices, spend analytics, savings tracking, approvals, workflows, documents, AI copilot, integrations, and mobile approvals — every activity cited with evidence and audit.

**Status: `TESTED` backend (89 pytest green, 75 API operations) + working Next.js 16 app — not yet `PRODUCTION READY` (see gate checklist in `docs/00-plan/ROADMAP.md` Phase 10).****

## Why VANTOR

Procurement teams juggle suppliers, RFQs, quotes, contracts, POs, invoices, spend, risk, and savings across disconnected tools. VANTOR connects them in one **Procurement Graph**:

```
SUPPLIERS → SOURCING → RFQs → QUOTES → NEGOTIATION → CONTRACTS → PURCHASES → INVOICES → SPEND → PERFORMANCE → RISK → SAVINGS
```

with `PROCUREMENT AI + HUMAN + AI COLLABORATION` on top — every AI answer cited with evidence, confidence, and human-review gates.

## What works today (tested, no mocks)

- [x] Backend API (FastAPI, 75 operations across 64 paths, 89 tests green): suppliers + scorecards + onboarding, RFQ→quote→award + optimizer, contracts + matching + e-sign, requisitions→PO→receipt→invoice with 3-way match, tiered approvals + SoD + budgets, spend ledger + intelligence + should-cost + price cases, catalogs, documents + extract + search, notifications, AI gateway + typed tools + HITL + nego sim, webhooks
- [x] AuthN/Z: Keycloak OIDC + RLS tenant isolation + RBAC + hash-chained audit + idempotency + rate limiting + security headers + honest `/ready`
- [x] Web app (Next.js 16 / React 19, typecheck + lint + build green): dashboard, suppliers grid, RFQs + comparison, contracts, orders, spend, documents, notifications, copilot, command palette (`Ctrl+K`)
- [x] Worker (RQ + Redis), free-only local stack (`docker compose up`), weekly CI with `pip-audit` + `npm audit` gates, operations runbook
- [ ] Write paths in the UI (RFQ create/award, PO approve/send/receipt/invoice, catalog, budgets, integrations, audit viewer), document OCR/embed/analyze, provider-side LLM streaming, realtime push, Android (Coming Soon — API-ready)

Never claim functionality that is not implemented. Phase 0 audit `VERIFIED`, Phases 3–4 `TESTED`, 5–8 `IN DEVELOPMENT`, 11 `PLANNED` (see `docs/00-plan/ROADMAP.md` and `docs/01-product/portfolio.md`).

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

See `SECURITY.md`. Never commit secrets. Report vulnerabilities privately. Keycloak OIDC + MFA planned; RLS tenant isolation mandatory.

## Contributing

See `CONTRIBUTING.md` + `CODE_OF_CONDUCT.md`.

CI is **weekly-only by owner request** (Mondays 05:17 UTC, plus manual dispatch) — there is
no PR or push trigger, so a red suite can sit unseen for up to a week. Run the same gates
locally before you push:

```powershell
python -m pytest backend/tests -q     # 89 tests
python scripts/verify_brain_links.py  # docs brain-link gate
cd frontend; npm run typecheck; npm run lint; npm run build
```

CI gates: secret guard, compose/env validation, required-docs presence, brain links,
`pytest`, Alembic upgrade/check/downgrade on real Postgres, OpenAPI drift
(`git diff --exit-code api/openapi.json`), frontend typecheck + lint + build, container
build, `pip-audit --strict`, `npm audit --audit-level=high`.

## License

**AGPL-3.0-or-later** © 2026 Digi Tracks — see `LICENSE`. Free to use, self-host,
and modify; network-service distribution of modified versions must publish source
(§13). Commercial exceptions: digi.tracks@outlook.com.

## Enquiries

Product: **VANTOR** by **Digi Tracks**. Email: **digi.tracks@outlook.com**.

## Roadmap summary

Phase 0 Discovery (audit) → 1 Architecture → 2 Design → 3 Foundation → 4 Core P2P → 5 Intelligence → 6 AI → 7 Premium UI → 8 Integrations → 9 Android → 10 Production hardening → 11 Portfolio extension (products 06–10). Details in `docs/00-plan/ROADMAP.md`.

> **Android app — Coming Soon (API-ready).** The `/api/v1` backend is already built
> for it (OIDC + RLS + approvals); the native Kotlin app starts as its own wave
> once device testing is available. See `docs/07-android/strategy.md`.
