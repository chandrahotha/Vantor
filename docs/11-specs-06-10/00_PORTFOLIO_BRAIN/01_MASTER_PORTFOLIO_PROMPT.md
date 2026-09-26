# Master Portfolio Build Prompt

You are building Products 06–10 of a serious enterprise procurement software portfolio. Implement every product end to end: data model, backend services, deterministic domain engine, AI orchestration, APIs, asynchronous jobs, evidence, audit, RBAC, UI, tests, synthetic data, documentation and deployment.

## Shared implementation baseline inherited from Products 01–05

- Frontend pattern: Next.js App Router + TypeScript + Tailwind + shadcn/ui + React Hook Form + TanStack Table + Zod.
- Backend pattern: Python 3.12+ + FastAPI + Pydantic + SQLAlchemy + Alembic.
- Data: PostgreSQL; object storage for source files; optional Redis/queue; optional DuckDB/Polars for analytical workloads.
- AI: provider abstraction, structured outputs, prompt/version registry, model/run ledger, tool registry, evidence-aware outputs.
- Optimization: OR-Tools where mathematical optimization is appropriate.
- Monetary values: integer minor units or Decimal; never float.
- Every normalized quantity stores UOM and conversion provenance.
- Evidence is immutable and location-aware.
- Audit is append-only/hash-chained and includes tenant, actor, request/correlation id, action, before/after hashes and reason where required.
- All APIs use the same envelope and error shape as the inherited Top-5 contract.

## Required architectural separation

`web → API → domain/application → deterministic engine → persistence`

AI may call typed read/analysis tools and may produce drafts/explanations. AI may not directly mutate domain tables, bypass authorization, approve awards, release financial commitments, or perform external communication without the same approval/material-action gate used by Product 01.

## Delivery standard

Do not stop at a working demo. Deliver:
- migrations and seed fixtures
- complete state machines
- negative and abuse cases
- tenant isolation tests
- authorization/object-level authorization tests
- idempotency tests
- deterministic golden vectors
- failure-recovery behavior
- observability
- accessibility and responsive UI
- local Docker environment
- CI gates
- release checklist
- deployment/runbook documentation
- synthetic public demo path
