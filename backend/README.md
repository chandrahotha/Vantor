# Backend — VANTOR API

The HTTP API behind VANTOR: one service exposing the whole procurement
domain, with tenancy, permissions, approvals and audit built into the
request path rather than bolted on around it.

**98 API operations across 84 paths**, all versioned under `/api/v1`.

**Stack:** Python 3.14 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic ·
PostgreSQL (with row-level security) · pgvector · Redis · Keycloak OIDC.

**Layout:** `app/{routers,services,models,core}/`. Routers are thin — they
validate, authorise and delegate. The rules live in `services/`, the data
model in `models/`, and the cross-cutting concerns (auth, tenancy,
idempotency, rate limiting, audit) in `core/`.

## Run it

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The schema is created on first boot for SQLite; for PostgreSQL, run the
migrations first:

```bash
alembic upgrade head
```

Interactive API reference: `http://localhost:8000/api/docs`. Health:
`/api/v1/health` (liveness) and `/api/v1/ready` (readiness).

## The API surface

| Domain | Paths | What it covers |
|---|---|---|
| `suppliers` | 9 | Supplier records, scorecards, qualification, onboarding |
| `contracts` | 10 | Contracts, obligations, renewal windows, e-signature handover |
| `purchase-orders` | 8 | Requisitions, POs, receipts, budget enforcement |
| `rfqs` | 7 | RFQ → quote → award, allocation |
| `ai` | 6 | Chat, streaming, typed tools, negotiation simulator |
| `invoices` | 6 | Invoice intake, matching, approval |
| `spend` | 6 | Spend cube, leakage, maverick spend, concentration, should-cost |
| `webhooks` | 5 | Outbound delivery, retries, subscriptions |
| `auth` | 4 | Sessions, personas, current user, provider config |
| `documents` | 4 | Upload, extract, chunk, search |
| `notifications` | 3 | Feed, read state, preferences |
| `approvals` | 2 | Approval queue, decisions |
| `audit-events` | 2 | Audit trail queries |
| `integrations` | 2 | Connected systems, health |
| `catalog` | 2 | Catalogue items |
| `requisitions` | 2 | Requisition intake |
| `ops` | 2 | Metrics, operational state |
| `budgets` | 1 | Budget pools |
| `health`, `ready`, `me` | 3 | Health, readiness, profile |

Every mutating workflow action accepts an idempotency key. Responses use one
envelope — `{data, pagination, error, requestId}` — and validation errors
come back typed, with field paths.

The full contract is committed at `api/openapi.json`, regenerated from the
code and checked by CI, so it cannot drift from what the server serves.

## Auth, tenancy and approvals

Two modes, one verification path:

- **`local`** (default) — the API issues its own passwordless sessions.
  Single-operator, never exposed to an untrusted network.
- **`oidc`** — Keycloak. The issuer must match the token's `iss` claim
  byte-for-byte; a mismatch is a 401 on every authenticated request.

Everything authenticated is tenant-scoped. On PostgreSQL, tenant isolation is
enforced twice — application filters *and* a row-level security backstop that
fails closed. Approval flows carry quorum requirements and separation of
duties. Every state change is written to a hash-chained audit log.

## Database

PostgreSQL is the primary store, with pgvector for document embeddings.
Migrations are Alembic, and the chain is linear with a single head.

CI checks the chain on every run, and runs the full migration drill —
`upgrade head` → `check` → `downgrade -1` → `upgrade head` — against a real
PostgreSQL on the weekly scheduled run and on a manual dispatch with
`full_suite: true`. The Postgres-backed tests (row-level security, foreign
keys, concurrency) run in the same job.

SQLite is supported for local development and the fast test tier. It is not
equivalent: SQLite has no row-level security, no `FOR UPDATE`, and no
composite foreign keys. A file-backed SQLite database — which is what the
single-container image runs on — gets one connection per thread rather than
one shared connection, so concurrent requests do not collide on the same
cursor.

## Tests

```bash
python -m pytest tests -q
```

**392 pytest collected** on the fast tier (383 pass, 9 need a real
PostgreSQL and skip without `PG_TEST_DATABASE_URL`). Auth and money paths
are covered without mocked identities or fabricated tenants — the API tests
exercise the real verification path rather than bypassing it.

```bash
ruff check app tests alembic   # lint
mypy app                        # type check
```

## Current limitations

- **The default test tier is SQLite.** It cannot prove row-level security
  or concurrency — `FOR UPDATE` is a no-op there. The Postgres tier
  (`pytest -m pg`, with `PG_TEST_DATABASE_URL`) is what covers those.
- **Search is lexical, not semantic.** Vectors are stored and compared for
  real, but a cosine over bag-of-words vectors is lexical. The response
  labels its mode honestly, and embeddings default to `disabled` — with no
  provider configured, chunks carry no vector and search is keyword-only.
- **No OCR.** A scanned PDF with no text layer is quarantined rather than
  read. `validate → store → extract → chunk → embed → audit` is real;
  OCR is not.
- **Storage is driver-selected.** `STORAGE_DRIVER=filesystem|s3` exists and
  the S3/MinIO path reads `S3_*`, but the default local stack uses the
  filesystem, so the S3 path is not exercised there.
- **Budget behaviour is a policy choice, not a default.** When a category has
  no budget row, `BUDGET_UNSET_POLICY` (`allow` or `block`) decides — there
  is no silent fallback.

## Documentation

- [Architecture](../docs/02-architecture/system.md) ·
  [Domain model](../docs/02-architecture/domain.md) ·
  [Database](../docs/02-architecture/database.md) ·
  [API design](../docs/02-architecture/api.md)
- [Security architecture](../docs/04-security/architecture.md) ·
  [Threat model](../docs/04-security/threat-model.md)
- [AI gateway](../docs/03-ai/architecture.md) ·
  [AI safety](../docs/03-ai/safety.md) ·
  [AI evaluation](../docs/03-ai/evaluation.md)
- [Deployment reference](../docs/08-deployment/local.md) ·
  [Operations runbook](../docs/09-operations/runbook.md)
- [Full documentation index](../docs/README.md)
