<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Local Deployment - VANTOR (free stack)

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

# S3-compatible object storage: no bundled container. MinIO withdrew its images
# from Docker Hub and quay.io, so a `minio` service here could never start - see
# the comment above the `keycloak` service in docker-compose.yml. Leave
# S3_ENDPOINT/S3_BUCKET blank in .env to use local-disk storage (UPLOAD_DIR)
# instead, which is what the template ships; set all four S3_* vars against any
# real S3-compatible endpoint you run yourself to use that instead.
```

| Service | Port | Profile | Needed for |
| --- | --- | --- | --- |
| postgres | 5432 | - | primary store + RLS |
| redis | 6379 | - | rate limiting, RQ queue, scheduler |
| keycloak | 8080 | - | OIDC login |
| keycloak-init | - | - | one-shot realm/role/client bootstrap; exits when done |
| beat | - | - | the RQ scheduler (expiry roll, webhook drain, spend snapshot) |
| ollama | 11434 | `ai` | local LLM + `nomic-embed-text` |

- **Keycloak is bootstrapped for you.** `keycloak` imports `deploy/keycloak/realm-vantor.json`
  with `--import-realm`, and `keycloak-init` then creates the roles, the worker's
  `vantor-service` machine identity and the bootstrap user, and keeps the client secret in step
  with `.env` on every start. Both are not behind a profile: without them there is no realm to log
  in to and no credential for the worker. To check what the realm ended up with, or to see why a
  grant is missing, read `docker compose logs keycloak-init`.
- Sign-in is Keycloak, and only Keycloak. The web app has no demo mode, no persona picker and no
  local credential path - a session exists if and only if the IdP returned a signed token carrying
  a tenant, and the API refuses a forged one in every environment including development.
- Object storage: no bundled MinIO (see above) - set `S3_*` against your own S3-compatible
  endpoint and create the bucket there, or leave them blank to use local-disk storage.
- Online AI instead of Ollama: no profile needed. Put a free key in `.env`
  (`OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `OPENCODE_ZEN_API_KEY`) and set
  `AI_PROVIDER` to that provider's name. Keys are never stored by the server and
  are never written to the audit log.
- **The scheduler is a service, so check it is running.** `beat` arms `roll_expiry` daily,
  `drain_webhooks` every 30s and `spend_snapshot` hourly. If it is not up, contract expiry
  rolling and spend rollups do not happen at all - the dashboard's live `expiring` query still
  works, but the stored statuses do not move. `docker compose logs beat` is the place to look.
- Staging/prod reuse same images; swap to managed Postgres/Redis/S3/OIDC via env only. Backups + restore drills, and the full production checklist: see `../09-operations/runbook.md`.

## Identity: which mode, and what each one needs

`AUTH_MODE` decides how anyone signs in, and the web app reads the answer from
the API (`GET /auth/config`) instead of a build-time constant — so one image
serves both modes and there is no stale IdP address baked into a bundle.

| `AUTH_MODE` | What it does | What you must set |
|---|---|---|
| `local` (the default when unset) | The API mints its own session. **Passwordless**: anyone who can reach the port is the local operator, with the full role set. | Nothing. Bind it to loopback or a trusted network. Never expose it. |
| `oidc` | Keycloak issues tokens; the browser is redirected there and comes back to `/auth/callback`. Authorization code + PKCE, no client secret in the bundle. | `OIDC_ISSUER`, `JWT_AUDIENCE`, and **`WEB_ORIGINS`** |
| `both` | Offers both paths. | Both rows above |

**`WEB_ORIGINS` is the one that breaks a first login.** Keycloak refuses an
authorization redirect to any origin that is not listed on the `vantor-web`
client, and the realm file can only ever name `localhost:3000` — so a deployment
on a real host that does not set this gets a sign-in button that cannot finish.
`keycloak-init` reconciles the client's redirect list from `WEB_ORIGINS` on
every start, the same way it reconciles the worker's secret:

```bash
WEB_ORIGINS=https://procurement.example.com    # comma-separate for several
AUTH_MODE=oidc
```

Plaintext `http://` origins are refused by provisioning unless they are
`localhost`, because an authorization code sent in the clear is a credential.

Two related variables are worth naming because they are easy to get wrong:

- `OIDC_ISSUER` must match the `iss` claim **byte for byte**. `127.0.0.1` and
  `localhost` are the same server and different issuers; a mismatch returns 401
  on every authenticated request while `/health` stays green.
- `JWT_AUDIENCE` must be the realm's web client id (`vantor-web`). A token minted
  for another client is not a token for this API. `test_config.py` asserts the
  default, `.env.example` and the provisioned realm all agree.

Revocation and MFA do not exist in this build — see
[`../04-security/architecture.md`](../04-security/architecture.md) for what is
implemented versus designed. A leaked access token is valid until it expires.
