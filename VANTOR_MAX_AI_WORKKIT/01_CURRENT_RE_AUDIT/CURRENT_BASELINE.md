# Current Repository Baseline

## Repository

- Archive: `Vantor-main.zip`
- Files: **671**
- Top-level directories: .env.example, .github, .gitignore, .pytest_cache, CHANGELOG.md, CODE_OF_CONDUCT.md, CONTRIBUTING.md, LICENSE, README.md, SECURITY.md, android, api, assets, backend, docker-compose.yml, docs, frontend, mkdocs.yml, pytest.ini, scripts, worker
- Backend Python application: `backend/app`
- Frontend: `frontend/app`, `frontend/components`, `frontend/lib`
- Worker: `worker`
- Migrations: `backend/alembic/versions` (20 files)

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
