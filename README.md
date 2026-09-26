<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# VANTOR — Intelligent Procurement Operating System

> **Value. Intelligence. Control.**

VANTOR is a unified, production-grade procurement operating system merging five procurement products into one coherent platform:

- Supplier intelligence (ex-SupplierRadar/Valtrix)
- Contract intelligence (ex-ContractGuard/Veridox)
- Cost intelligence (ex-CostPilot/Costryn)
- Sourcing / RFQ intelligence (ex-RFQLens/QuotientX)
- Procurement AI agent (ex-ProcurementOS-Agent)

**Status: `PLANNED` — docs-first V1 scaffold. Not production-ready. See `docs/00-plan/ROADMAP.md` and `docs/`.**

## Why VANTOR

Procurement teams juggle suppliers, RFQs, quotes, contracts, POs, invoices, spend, risk, and savings across disconnected tools. VANTOR connects them in one **Procurement Graph**:

```
SUPPLIERS → SOURCING → RFQs → QUOTES → NEGOTIATION → CONTRACTS → PURCHASES → INVOICES → SPEND → PERFORMANCE → RISK → SAVINGS
```

with `PROCUREMENT AI + HUMAN + AI COLLABORATION` on top — every AI answer cited with evidence, confidence, and human-review gates.

## What works today (V1 scaffold)

- [x] Public repo structure + full prerequisite documentation
- [x] System/domain/DB/API/AI/security architecture (planned, not yet implemented)
- [x] Vantor brand + logo assets (`assets/brand/`, `docs/06-brand/logo.md`)
- [x] Free-only local stack via `docker-compose.yml` (Postgres+pgvector, Redis, MinIO, Keycloak, Ollama)
- [ ] Backend / frontend implementation — `PLANNED` (starts Phase 3, pending repository audit)
- [ ] AI Copilot, document pipeline, Android — `PLANNED`

Never claim functionality that is not implemented. Phase 0 audit `VERIFIED` (see `docs/00-plan/REPOSITORY_AUDIT.md`) — implementation starts Phase 3.

## Quickstart (local, 100% free)

Prerequisites: Docker + Docker Compose, Node 20+, Python 3.11+ (for worker later), Git.

```powershell
Copy-Item .env.example .env
docker compose up -d postgres redis minio keycloak ollama
# backend / frontend / worker start after Phase 3 implementation
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
backend/  frontend/  worker/  android/  api/  scripts/
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

Apache-2.0 — see `LICENSE`.

## Roadmap summary

Phase 0 Discovery (audit) → 1 Architecture → 2 Design → 3 Foundation → 4 Core P2P → 5 Intelligence → 6 AI → 7 Premium UI → 8 Integrations → 9 Android → 10 Production hardening. Details in `docs/00-plan/ROADMAP.md`.
