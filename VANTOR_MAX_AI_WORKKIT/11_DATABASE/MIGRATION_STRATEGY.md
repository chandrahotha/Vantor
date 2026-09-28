<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Migration Strategy

All schema changes are forward-compatible, reversible where feasible, idempotent and tested against a copy of current production-like data. Large backfills use online/background strategies.

## Now implemented (2026-09-28)

23 migrations, one linear chain with a single head, `upgrade` and `downgrade` on every one,
enforced by `scripts/audit_migrations.py` in CI (it also imports every module, so a migration
that cannot even be loaded fails the gate). Reversible and idempotent by construction; the one
deliberate exception is documented in the migration itself — `0016` is a metadata-only column
widening on Postgres.

Forward compatibility is not universally true, and the ledger should say so: a `NOT NULL`
column with no default, or a narrowing type change, is a breaking edit against a live table.
`0023_tenant_timezone` adds a *nullable* column for exactly that reason.

**PostgreSQL verification is partial, and this is the significant caveat.** RLS policy behaviour
was proven against a genuine PostgreSQL 18 instance on 2026-09-26 with a non-superuser app role
(runbook §7), but the exact revision tested was not recorded, so it cannot be assumed to cover
everything added since. `PG_TEST_DATABASE_URL` is not available in the current development
environment, so the PG-gated tests skip here and `alembic check` has never run. Treat every
backfill, the pgvector HNSW index, the partial unique indexes and the large table rewrites as
unverified against a real engine.
