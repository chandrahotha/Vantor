<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Backend — VANTOR

**Status: `IN DEVELOPMENT` — Phase 3 Foundation landing (stack DECIDED — see `../docs/10-decisions/ADR-007-fastapi-backend.md`).**

Stack: **FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic**, Postgres + RLS primary, RQ + Redis queue, S3-compatible storage, Keycloak OIDC.

Layout: `app/{routers,services,models,core}/` converging the 5 source trees per `../docs/00-plan/MIGRATION_PLAN.md` (canonical audit+idempotency from SupplierRadar, quorum approvals from ProcurementOS, JWKS auth from ContractGuard).
API: `/api/v1/...`, OpenAPI generated from code, typed schemas, idempotency keys, versioning.

## Run

```powershell
Copy-Item ..\..\\.env.example ..\..\\.env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
pytest -q
```

## Gates (Phase 3)

- tenant-isolation + auth tests green (`tests/test_tenant_isolation.py`, `tests/test_auth.py`)
- Alembic baseline applies clean on pgvector/pg16 (`alembic upgrade head`)
- No fake auth, no mock data, no hardcoded tenants — fail-closed 401/403.
