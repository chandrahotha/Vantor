<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Local Deployment — VANTOR (free stack)

**Status: `IMPLEMENTED` (compose file + images).**

```powershell
Copy-Item .env.example .env        # fill secrets; never commit .env

# Core stack. This is all you need: the AI gateway ships in `disabled` mode,
# which answers UNKNOWN with confidence 0 rather than failing to connect.
docker compose up -d postgres redis keycloak
docker compose up -d --build backend frontend worker beat
docker compose ps
```

## Optional profiles

Two services are behind a Compose profile so the default stack stays small and
works with no model downloads. Name them explicitly to enable:

```powershell
# Local models (AI gateway + real document embeddings)
docker compose --profile ai up -d ollama
docker exec vantor-ollama-1 ollama pull llama3.1:8b
docker exec vantor-ollama-1 ollama pull nomic-embed-text
# then set AI_PROVIDER=ollama (and EMBEDDING_PROVIDER=ollama) in .env and
# restart the backend.

# S3-compatible object storage
docker compose --profile storage up -d minio
```

| Service | Port | Profile | Needed for |
| --- | --- | --- | --- |
| postgres | 5432 | — | primary store + RLS |
| redis | 6379 | — | rate limiting, RQ queue, scheduler |
| keycloak | 8080 | — | OIDC login |
| ollama | 11434 | `ai` | local LLM + `nomic-embed-text` |
| minio | 9000 / 9001 | `storage` | S3-compatible blobs |

- First-run Keycloak: `admin / admin-change-me` → create realm `vantor`, client `vantor-web`, roles from `../04-security/architecture.md`.
- MinIO: create bucket `vantor-docs` (tenant prefixes enforced in code).
- Online AI instead of Ollama: no profile needed. Put a free key in `.env`
  (`OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `OPENCODE_ZEN_API_KEY`) and set
  `AI_PROVIDER` to that provider's name. Keys are never stored by the server and
  are never written to the audit log.
- Staging/prod reuse same images; swap to managed Postgres/Redis/S3/OIDC via env only. Backups + restore drills: see `../09-operations/runbook.md`. Full prod checklist: masterdoc §55.
