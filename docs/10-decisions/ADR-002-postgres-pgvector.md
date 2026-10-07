<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ADR-002 - PostgreSQL + pgvector as primary

- Context: transactional P2P + document/AI search in one product.
- Decision: Postgres 16 + pgvector; Redis cache/queue; MinIO bytes. No Elastic at V1.
- Alternatives: Postgres + Elastic, Mongo + vector DB.
- Consequences: +one primary to operate/back up; +RLS tenancy; −revisit if FTS/vector scale proves insufficient (measure first).
