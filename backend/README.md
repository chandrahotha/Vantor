<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Backend — VANTOR

**Status: `TESTED` — 90 API operations across 78 paths, 315 pytest collected.** Not `PRODUCTION READY`
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

- **315 tests collected** (313 pass, 2 skip for want of PostgreSQL), no mocks in the auth or money
  paths. Every API test mints a real RS256 JWT and verifies it through the real JWKS path;
  `unittest.mock` appears nowhere in the suite.
- Tenant isolation: application filters **and** the RLS backstop.
  `test_no_unpinned_sessions_outside_request_cycle` fails the build if any code opens a session
  without `pinned_session()` — SQLite cannot catch that class of bug, so it is checked structurally.
- Alembic chain 0001–0023 is linear with a single head; CI runs `upgrade head` → `check` →
  `downgrade -1` → `upgrade head` on real Postgres.
- No fake auth, no mock data, no hardcoded tenants — fail-closed 401/403.

## What is NOT here (do not assume it)

- **The cosine re-rank is real geometry, not semantics.** Vectors are stored and compared for
  real (pgvector column, HNSW index, dimension validation), but a plain cosine over bag-of-words
  vectors is lexical, not semantic. `/documents/search` labels its mode honestly in the response
  and the label is asserted in tests, because "semantic search" in a demo would be a lie.
  Embeddings default to `disabled`; with no provider configured, chunks carry no vector and
  search is keyword-only rather than ranked on zero vectors.
- **`test_tenant_isolation.py` asserts RLS policy *SQL shape*, not runtime behaviour**, because
  the test DB is SQLite and has no RLS. The policy was proven against genuine PostgreSQL 18 once,
  on 2026-09-26 (see `../docs/09-operations/runbook.md` §7), but that run's revision was not
  recorded and no PostgreSQL is available in the current environment.
- **The RLS test only covers the baseline migration.** It checks that `0001_baseline.py` defines
  its policies; the 13 later migrations that also enable RLS are uncovered, so a new tenant table
  could ship with no policy and the suite would stay green.
- **The budget row lock is unproven under concurrency.** `check_budget` takes
  `with_for_update` on the budget row before reading the aggregate, which is the right mechanism,
  but the concurrency test the docstring once referred to does not exist and SQLite renders no
  `FOR UPDATE`. Treat the ceiling as enforced by construction, not verified.
- **`check_budget` is per (category, period).** A tenant that spends in a category with no budget
  row set is unchecked — `{"checked": false}` is returned and the approval proceeds.
- **Document OCR is still absent.** `validate → store → extract → chunk → embed → audit` are
  real; a scanned PDF with no text layer is quarantined, not OCR'd.
- **Storage is driver-selected, not local-only.** `STORAGE_DRIVER=filesystem|s3` exists and the
  S3/MinIO path reads `S3_*`, but the compose default is filesystem, so the S3 path is not
  exercised by the default local stack.
