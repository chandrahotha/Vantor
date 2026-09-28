<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Database Architecture — VANTOR

**Status: `PLANNED`. Primary: PostgreSQL 16 + pgvector. No second primary DB without ADR.**

## Choices
- **Postgres (+pgvector):** transactions + RLS tenant isolation + vector search for docs. One primary to operate.
- **Redis:** cache (tenant-aware keys), queues, rate-limit buckets, realtime pub/sub. Not a system of record.
- **MinIO/S3:** document bytes + versions; DB holds metadata/chunks/embeddings pointers. Tenant-prefixed buckets/paths.
- **No Elastic/OpenSearch at V1:** Postgres FTS + pgvector suffice; add only on measured search pain.

## Rules
- Every row: `id (uuid), tenant_id/org_id, created_at/updated_at/created_by/updated_by`, FKs + check constraints + deliberate indexes (tenant first, then lifecycle/state, then time).
- RLS policies enforce `tenant_id = current_setting('app.tenant_id')`; service role bypasses only in migrations; tests assert cross-tenant invisibility.
- Migrations versioned, reversible, with seed only for reference data (roles, categories) — never fake suppliers/transactions.
- Backups: nightly pg_dump + WAL (prod managed PITR); restore drilled quarterly; retention + privacy controls documented in runbook.

## Per-tenant business timezone

`organizations.timezone` holds an IANA zone for the tenant. It is **nullable and defaults to
empty, which means "inherit"** — the column was added by migration `0023` and backfilled empty,
so an upgrade changes no existing row. Nullability is deliberate: a `NOT NULL` column with a
default is a lock- and correctness-hostile edit on a live table.

Business dates are computed in the resolved zone, not the server's. Resolution is
tenant → `CONTRACT_TIMEZONE` (deployment default) → UTC, and a zone that cannot be loaded falls
through to the next level rather than raising. A buyer at UTC-12 reaches their own 1 January
twelve hours before a UTC server does, so a single deployment-wide zone is wrong for nearly all
tenants of a system whose users span countries.

## Caveats a reader should not skip

- **PostgreSQL verification is partial, and the boundary is not recorded.** RLS policy behaviour
  was proven against a genuine PostgreSQL 18 instance on 2026-09-26 with a non-superuser app
  role — see runbook §7. The exact revision tested was not written down, so it cannot be assumed
  to cover migrations added since. No PostgreSQL is available in the current development
  environment, so the PG-gated tests (`test_pg_infrastructure.py`) skip here, and the pgvector
  HNSW index, the partial unique indexes and the `FOR UPDATE SKIP LOCKED` drains are unverified
  on a real engine.
- **The RLS test only covers the baseline migration.** It asserts `0001_baseline.py` defines its
  policies, but 13 later migrations also enable RLS and no test covers them. A new tenant table
  could ship without a policy and the suite would stay green.
- `current_setting('app.tenant_id', true)` is called with the `missing_ok` flag so that an absent
  setting yields NULL and therefore matches no rows — fail-closed rather than fail-open.
