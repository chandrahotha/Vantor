<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Operations Runbook — VANTOR

**Status: `IMPLEMENTED` — matches the shipped stack (compose services, real endpoints).**

## 1. Health & readiness (real endpoints, no fake green)

| Probe | What it checks | Healthy when |
|---|---|---|
| `GET /api/v1/health` | process alive | always 200 when code runs |
| `GET /api/v1/ready` | Postgres (`SELECT 1` + `alembic_version` head) + Redis `PING` | 200; anything else → 503 with per-check detail |

`ready` reports `down: unmigrated` when `alembic_version` is absent — the load
balancer must NOT route there. Redis down does not fail readiness alone but is
reported (rate limiter runs fail-open, see §5).

## 2. Logs (JSON access lines)

Every non-probe request emits one JSON line: `ts, requestId, method, path,
status, ms, tenant`. Collection: `docker compose logs -f backend`, or ship
stdout to Loki/CloudWatch. Correlate user reports via `X-Request-ID`
(every error envelope carries `requestId`).

## 3. Backups (local → prod path)

- **Local:** `docker compose exec postgres pg_dump -U vantor vantor > vantor-$(date +%F).sql`
- **Uploads:** `uploads/` is a plain directory — back it up alongside the DB (keys are `tenant/sha[0:2]/sha`).
- **Prod path:** managed Postgres PITR + object-storage versioning + Keycloak realm export; quarterly restore drill with a signed record in `CHANGELOG.md`.

## 4. Common incidents

| Symptom | Check | Fix |
|---|---|---|
| 401 everywhere | Keycloak down? `curl $KEYCLOAK_URL/realms/vantor` | restart keycloak; tokens expire naturally |
| 403 "no tenant" | IdP claim mapping | ensure `tenant_id`/`org_id` claim in realm mapper |
| 409 storm on writes | client retrying without `Idempotency-Key` | add key; replays return original + `Idempotent-Replayed` |
| 429 `RATE_LIMITED` | `X-RateLimit-Remaining` headers | raise `RATE_LIMIT_*_PER_MIN` or spread load |
| 503 `/ready` unmigrated | migrations not applied | `cd backend && alembic upgrade head` |
| Audit `valid:false` | tamper or clock skew | freeze writes, `GET /audit-events/verify` message pinpoints row, restore from backup |
| AI 502 `AI_PROVIDER_FAILED` | provider down/unconfigured | switch `AI_PROVIDER` (ollama/opencode/nvidia/disabled); failures name the provider by design |

Sev1 (tenant leak / financial mis-post): freeze deploys, preserve `audit_events`
(hash chain is the evidence), rotate `JWT_SECRET`/IdP clients, notify
**digi.tracks@outlook.com**. AI incident: set `AI_PROVIDER=disabled`, keep the
`AI_TOOL_EXECUTED` trail, post-mortem ADR.

## 5. Rate limiter & idempotency ops

- Redis down ⇒ limiter fail-open (`X-RateLimit-Bypass` header set); restores automatically on reconnect.
- Idempotency keys are tenant+method+path+body bound; replays carry `Idempotent-Replayed: true`.

## 6. Worker ops

- `python worker/enqueue.py roll_expiry` (needs `SERVICE_API_TOKEN` — Keycloak service account).
- Queues: `default`, `documents`. Failed RQ jobs stay in the registry for inspection — never silently dropped.

See Brain → [`08-deployment/local.md`](../08-deployment/local.md), [`04-security/threat-model.md`](../04-security/threat-model.md).
