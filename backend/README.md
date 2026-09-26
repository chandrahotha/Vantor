<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Backend — VANTOR

**Status: `PLANNED` (stack DECIDED — see `../docs/10-decisions/ADR-007-fastapi-backend.md`).**

Stack: **FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic** (audit-verified 5/5 convergence), Postgres + RLS primary, RQ + Redis queue, S3-compatible storage, Keycloak OIDC.

Planned layout: `app/{routers,services,models,core,tools,engine,migrations}/` converging the 5 source trees per `../docs/00-plan/MIGRATION_PLAN.md` (canonical audit+idempotency from SupplierRadar, quorum approvals from ProcurementOS, JWKS auth from ContractGuard).
API: `/api/v1/...`, OpenAPI generated from code, typed schemas, idempotency keys, versioning.
