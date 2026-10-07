<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# System Architecture - VANTOR

**Status: `PLANNED`. Principle: modular monolith first, API-first for web + Android.**

## Topology (free, self-hostable)

```
Next.js web ─┐
Android ─────┼─→ API (/api/v1) → modules → Postgres+pgvector ─┐
             │                    ├→ Redis (cache/queue)       │→ MinIO (docs)
             │                    ├→ Worker (OCR/embed/notify) │→ Keycloak (OIDC)
             │                    └→ AI Gateway (Ollama default│→ free-tier fallbacks)
```

## Module boundaries
`identity supplier sourcing(rfq/quote/award) contract spend purchase approval workflow document ai notification integration audit`. Each: domain → service → typed API → events → tests. Shared kernels only for tenanting, authz, audit, config, errors.

## Why not microservices/Kafka/K8s now
No audit evidence they are needed; ops cost exceeds benefit at V1 scale. Horizontal API + worker scaling + read optimization suffice. Revisit via ADR with load data.

## Events (only where valuable)
`SUPPLIER_* RISK_CHANGED, RFQ_* QUOTE_* CONTRACT_* PO_* INVOICE_* APPROVAL_* SAVINGS_OPPORTUNITY_DETECTED` via DB-outbox → worker → webhooks/notifications. No event theater.

## Config & environments
`.env.example` canonical; local `docker compose`, staging/prod same images + managed Postgres/Redis/S3/OIDC in cloud. Secrets in manager only.

## Perf/scale
Connection pooling, deliberate indexes, pagination/virtualized grids, cached reference data (tenant-aware), async doc/AI paths, provider failover. Measure before optimizing.
