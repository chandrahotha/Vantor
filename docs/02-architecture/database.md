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
