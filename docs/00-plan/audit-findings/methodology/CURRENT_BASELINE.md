<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../../BRAIN.md) · [Docs index](../../../README.md)

# Current Repository Baseline

## Repository

- Archive: `Vantor-main.zip`
- Files: **842** tracked (the original audit counted 671; the tree has grown since)
- Top-level directories: .env.example, .github, .gitignore, .pytest_cache, CHANGELOG.md, CODE_OF_CONDUCT.md, CONTRIBUTING.md, LICENSE, README.md, SECURITY.md, android, api, assets, backend, docker-compose.yml, docs, frontend, mkdocs.yml, pytest.ini, scripts, worker
- Backend Python application: `backend/app`
- Frontend: `frontend/app`, `frontend/components`, `frontend/lib`
- Worker: `worker`
- Migrations: `backend/alembic/versions` - **23 migrations** (`0001`-`0023`, plus `__init__.py`).
  One linear chain, single head, `upgrade` and `downgrade` on each, gated by
  `scripts/audit_migrations.py`. RLS policy behaviour was proven against genuine PostgreSQL 18 on
  2026-09-26 (runbook §7), but the revision tested was not recorded and no PostgreSQL is available
  in the current environment, so the PG-gated tests skip here.

## Current stack from live manifests

### Backend

FastAPI 0.141.1, Starlette 1.7.0, Uvicorn 0.34.0, Pydantic 2.10.4, SQLAlchemy 2.0.36, Alembic 1.14.0, psycopg 3.2.9, pgvector 0.3.6, PyJWT 2.15.0, Redis 5.2.1, RQ 1.16.2, Python 3.13 image.

### Frontend

Next.js **16.3.6**, React **19.3.0**, TypeScript **5.9.3**, Keycloak JS **26.2.4**, Node 22 runtime image. The current source is newer than several committed docs that describe earlier versions.

### Persistence / infrastructure

PostgreSQL/pgvector, Redis, Keycloak, optional MinIO, optional Ollama, Docker Compose, RQ worker/scheduler.

## Frontend route inventory

- frontend/app/contracts/page.tsx
- frontend/app/copilot/page.tsx
- frontend/app/documents/page.tsx
- frontend/app/governance/page.tsx
- frontend/app/integrations/page.tsx
- frontend/app/negosim/page.tsx
- frontend/app/notifications/page.tsx
- frontend/app/orders/page.tsx
- frontend/app/page.tsx
- frontend/app/requisitions/page.tsx
- frontend/app/rfqs/page.tsx
- frontend/app/spend/page.tsx
- frontend/app/suppliers/[id]/page.tsx
- frontend/app/suppliers/page.tsx

## Current architecture shape

The repository is a modular monolith with separate worker and frontend deployments. Business modules are primarily organized as FastAPI routers + SQLAlchemy models/services, while the frontend uses route-level client components and a small shared UI primitive layer.

## Primary maturity observation

The core workflow is real and substantial, but high-risk gaps cluster at transaction boundaries, authorization consistency, durable integrations/storage, AI evidence enforcement, production bootstrap, and UI/UX maturity.

## What has changed since this baseline was taken (2026-09-28)

Recorded so the staleness above is not mistaken for a description of the current tree.

- **Worker least privilege.** The worker's service account was granted `Super Admin` +
  `Procurement Admin` + `Procurement Manager`; it now holds one role, `Service Identity`,
  covering only the expiry roll and the webhook drain.
- **Per-tenant business timezone.** `organizations.timezone` plus migration `0023`, replacing a
  single deployment-wide `CONTRACT_TIMEZONE` for every tenant.
- **A CSP on the web app's own responses.** The API's policy governed the wrong origin.
- **Two post-audit defects fixed:** the sourcing optimizer had no role gate, and the webhook
  drain defaulted its tenant scope to every tenant.
- **Test totals:** backend 315 collected (313 passed, 2 skipped for want of PostgreSQL), frontend
  106 passed across 10 files.

Still true, and still the reason this is not closer to production: no PostgreSQL run, no browser
E2E/accessibility/visual gate, and no resolved image digests.
