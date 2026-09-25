<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Local Deployment — VANTOR (free stack)

**Status: `IMPLEMENTED` (compose file) / `PLANNED` (backend images, Phase 3).**

```powershell
Copy-Item .env.example .env        # fill secrets; never commit .env
docker compose up -d postgres redis minio keycloak ollama
docker compose ps
docker exec vantor-ollama-1 ollama pull llama3.1:8b
docker exec vantor-ollama-1 ollama pull nomic-embed-text
```

- Postgres `5432`, Redis `6379`, MinIO API `9000`/console `9001`, Keycloak `8080`, Ollama `11434`.
- First-run Keycloak: `admin / admin-change-me` → create realm `vantor`, client `vantor-web`, roles from `../04-security/architecture.md`.
- MinIO: create bucket `vantor-docs` (tenant prefixes enforced in code).
- Staging/prod reuse same images; swap to managed Postgres/Redis/S3/OIDC via env only. Backups + restore drills: see `../09-operations/runbook.md`. Full prod checklist: masterdoc §55.
