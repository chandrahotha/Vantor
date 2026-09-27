<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Backend — VANTOR

**Status: `TESTED` — 90 API operations across 78 paths, 298 pytest collected.** Not `PRODUCTION READY`
(Phase 10 gate, see `../docs/00-plan/ROADMAP.md`).

Stack: **FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic**, Postgres + RLS primary, RQ + Redis
queue, Keycloak OIDC. (FastAPI decided in `../docs/10-decisions/ADR-007-fastapi-backend.md`.)

Layout: `app/{routers,services,models,core}/`. It converges the 5 audited source trees per
`../docs/00-plan/MIGRATION_PLAN.md` — canonical audit + idempotency from SupplierRadar, quorum
approvals from ProcurementOS, JWKS auth from ContractGuard. It also carries the native modules for
portfolio products 06–10 (see `../docs/01-product/portfolio.md`).

API: `/api/v1/...`, OpenAPI generated from code and committed to `../api/openapi.json`.
CI fails if the committed contract drifts from the code.

## Run

```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
python -m pytest tests -q
```

## Gates

- **298 tests collected**, no mocks in the auth or money paths. Every API test mints a real RS256 JWT
  and verifies it through the real JWKS path; `unittest.mock` appears nowhere in the suite.
- Tenant isolation: application filters **and** the RLS backstop.
  `test_no_unpinned_sessions_outside_request_cycle` fails the build if any code opens a session
  without `pinned_session()` — SQLite cannot catch that class of bug, so it is checked structurally.
- Alembic chain 0001–0015 is linear with a single head; CI runs `upgrade head` → `check` →
  `downgrade -1` → `upgrade head` on real Postgres.
- No fake auth, no mock data, no hardcoded tenants — fail-closed 401/403.

## What is NOT here (do not assume it)

- **Document pipeline is ~30%.** `validate → store → extract → chunk → audit` are real. OCR,
  embedding, semantic index, analysis, evidence and review are absent. `embedding` is an empty
  dict; search is `ILIKE` only.
- **Storage is local disk.** `S3_*` appears in `.env.example` and MinIO runs in compose, but no
  code reads those variables.
- **`/ai/stream` is not provider-streamed.** Frames are cut from the completed response; each
  frame carries `"streamed": false`.
- **`evidence` is always `[]`.** The gateway returns an empty list on every path.
- **Requisitions are untested at the API level.** `POST /requisitions` and `/submit` have no test,
  so the tier-seeding logic is unverified.
- **`test_tenant_isolation.py` asserts RLS policy *SQL shape*, not runtime behaviour**, because
  the test DB is SQLite and has no RLS. Only CI's Postgres run exercises the real policy.
