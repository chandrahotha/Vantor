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
| keycloak-init | — | — | one-shot realm/role/client bootstrap; exits when done |
| beat | — | — | the RQ scheduler (expiry roll, webhook drain, spend snapshot) |
| ollama | 11434 | `ai` | local LLM + `nomic-embed-text` |
| minio | 9000 / 9001 | `storage` | S3-compatible blobs |

- **Keycloak is bootstrapped for you.** `keycloak` imports `deploy/keycloak/realm-vantor.json`
  with `--import-realm`, and `keycloak-init` then creates the roles, the worker's
  `vantor-service` machine identity and the bootstrap user, and keeps the client secret in step
  with `.env` on every start. Both are not behind a profile: without them there is no realm to log
  in to and no credential for the worker. To check what the realm ended up with, or to see why a
  grant is missing, read `docker compose logs keycloak-init`.
- Sign-in is Keycloak, and only Keycloak. The web app has no demo mode, no persona picker and no
  local credential path — a session exists if and only if the IdP returned a signed token carrying
  a tenant, and the API refuses a forged one in every environment including development.
- MinIO: create bucket `vantor-docs` (tenant prefixes enforced in code).
- Online AI instead of Ollama: no profile needed. Put a free key in `.env`
  (`OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `OPENCODE_ZEN_API_KEY`) and set
  `AI_PROVIDER` to that provider's name. Keys are never stored by the server and
  are never written to the audit log.
- **The scheduler is a service, so check it is running.** `beat` arms `roll_expiry` daily,
  `drain_webhooks` every 30s and `spend_snapshot` hourly. If it is not up, contract expiry
  rolling and spend rollups do not happen at all — the dashboard's live `expiring` query still
  works, but the stored statuses do not move. `docker compose logs beat` is the place to look.
- Staging/prod reuse same images; swap to managed Postgres/Redis/S3/OIDC via env only. Backups + restore drills, and the full production checklist: see `../09-operations/runbook.md`.
