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
| `BUDGET_EXCEEDED` on approve | PO would breach the category ceiling for the period | raise the ceiling via `POST /api/v1/budgets` (or the Governance page) — do not bypass the gate |
| `APPROVAL_SOD` 403 | requester == approver | a second human with the right role must approve; this is by design, never disable |
| Idempotent replay returns stale data | key reused with a different body | keys are body-bound; use a fresh key per distinct action |
| Notifications badge never clears for one user | broadcast row read state | read state is per-recipient (`read_by`); one user reading no longer silences the tenant |

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
- **Nothing schedules these jobs.** There is no beat/cron sidecar in `docker-compose.yml` and no
  periodic enqueue, so `roll_expiry` and `spend_snapshot` run only when a human invokes them. Until a
  scheduler lands, **contract expiry rolling and spend rollups are not automatic in any environment**,
  including local compose. Either trigger them by hand or treat the "Contracts flagged expiring"
  dashboard count as stale.
- The `documents` queue is currently **dead**: `worker.py` listens on it, but no job functions are
  registered for it and no backend code enqueues to it. It is reserved for the Phase 5 OCR/embed wave.
- No backend code calls the worker — `worker/enqueue.py` is the only enqueue path, and it is manual.

## 6a. RLS session discipline (added 2026-09-26)

Application-level `tenant_id` filters are mandatory but **not sufficient**: Postgres RLS is the
backstop, and RLS only engages if the session has `app.tenant_id` set.

- Request-scoped code uses the `db_for_actor` dependency, which pins via `get_db(actor.tenant_id)`.
- Code **outside** the request cycle (middleware, SSE generators, background work) must use
  `core.tenant.pinned_session(tenant_id)`. A raw `get_session_factory()()` looks identical on SQLite
  and silently fails on Postgres, because the RLS `WITH CHECK` rejects the write and a broad
  `except` hides it. This is not hypothetical: it broke idempotency and the AI audit trail in
  production semantics while the test suite stayed green.
- `test_no_unpinned_sessions_outside_request_cycle` scans the source and fails the build on a
  regression. If you add a session outside the request cycle, use the pinned helper.
- Never call `pinned_session("")` — an empty tenant sets an empty GUC, which makes every RLS
  predicate false and *hides* rows rather than leaking them. The helper no-ops on an empty tenant for
  exactly that reason.

## 7. RLS proof (verified 2026-09-26 on genuine Postgres 18)

Policy shape (all migrations): `USING/WITH CHECK (tenant_id = current_setting('app.tenant_id', true))`.
Proven with a non-superuser app role: tenant A sees only A's rows, tenant B only
B's, no context sees zero rows (fail-closed), cross-tenant INSERT blocked by policy.

**Hard rule:** the runtime DB role must be NON-superuser and must NOT own the
tables (owners and superusers bypass RLS by PostgreSQL design — verified: the
same policy is unenforced for superusers). Provision via:
`CREATE ROLE vantor_app NOSUPERUSER LOGIN; GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO vantor_app;`
(migrations run as a separate owner role). Never point `DATABASE_URL` at a superuser in prod.

See Brain → [`08-deployment/local.md`](../08-deployment/local.md), [`04-security/threat-model.md`](../04-security/threat-model.md).
