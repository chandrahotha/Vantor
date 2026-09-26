<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ADR-007 — FastAPI backend (audit-decided)

- Context: unified-stack decision was deferred to the Phase 0 audit ("keep what audit finds"). Audit 2026-09-26 verified: 5/5 source backends are Python FastAPI; 0/5 use NestJS/Node.
- Decision: Vantor backend = **FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic**, Postgres primary, RQ + Redis queue. No NestJS service; no Python sidecar — Python is the core.
- Alternatives: NestJS core + Python ai-worker (rejected: zero evidence of TS backend strength; all 5 deterministic engines are Python), single Next.js API routes (rejected: procurement math + workers need a real Python service).
- Consequences: +direct port of 5 proven codebases with tests; +one language for backend/AI/worker; −must still build API discipline (OpenAPI from code, envelope standard) and replace snapshot/in-memory stores with relational RLS.
