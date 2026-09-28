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
| AI 502 `AI_PROVIDER_FAILED` | provider down / key missing | the message names the provider and the exact env var. `GET /api/v1/ai/providers` shows which are configured. Switch `AI_PROVIDER` to another of `disabled` / `ollama` / `opencode` / `openrouter` / `opencode-zen` / `omnirouter` / `nvidia` / `openai` / `anthropic` / `gemini`; failures never fall back silently to another provider |
| AI 422 `AI_PROVIDER_UNKNOWN` | client asked for a provider this build does not know | `error.details.known` lists the valid names — a client bug, not an outage |
| `UNKNOWN_REFERENCE` 422 on write | a `category_id` / `document_id` points at nothing in this tenant | the field name is in `error.details.field`. Create the parent first; the API refuses to store an orphan because there is no FOREIGN KEY to catch it |
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

- **The scheduler exists and is a service.** `worker/beat.py` runs as the `beat` container
  (`docker compose up -d beat`); it arms `roll_expiry` (daily), `drain_webhooks` (every 30s) and
  `spend_snapshot` (hourly) and promotes them onto the `default` queue. Intervals are overridable
  with `ROLL_EXPIRY_INTERVAL_S`, `WEBHOOK_DRAIN_INTERVAL_S`, `SPEND_SNAPSHOT_INTERVAL_S`; a
  non-positive or unparseable value falls back to the default rather than becoming a tight loop.
- **The scheduler used to die on boot.** It called `RQScheduler(queue_name=…)` and
  `scheduler.schedule(…)`, neither of which exists in the pinned rq 1.16.2, so the container
  exited immediately and no recurring job had ever run in any environment (B-34). The unit tests
  in `worker/tests/` run in CI and pin the real rq surface.
- `python worker/enqueue.py roll_expiry` still runs one job immediately, by hand. The worker
  authenticates with a Keycloak client-credentials grant; `SERVICE_API_TOKEN` remains only as an
  escape hatch for environments where the grant is unavailable.
- Queues: `default`, `documents`. Failed RQ jobs stay in the registry for inspection — never silently dropped.
- **The worker holds one role, `Service Identity`, and not an administrative one.** It can run the
  contract expiry roll and the webhook drain, and nothing else — it cannot activate, terminate,
  sign, review or renew a contract or approve a requisition. If you need it to do more, do not
  widen the role; the fix is a new narrowly-scoped role, because widening `Service Identity`
  silently widens what every leaked worker secret can reach. `test_realm_parity.py` enforces the
  grant and the refusals.
- **The worker only acts on its own tenant.** Both its operations go through tenant-scoped routes,
  so a service token scoped to tenant A rolls A's contracts and delivers A's webhooks only. In a
  multi-tenant deployment you need one service account per tenant, or a deliberately
  cross-tenant identity — which is a different design decision, not a config tweak. Do not solve
  it by removing the tenant filter from a query. (B-18, still open by design.)
- **What "expiring" means depends on the tenant's timezone, not the server's.** The roll evaluates
  "within N days" in `organizations.timezone`, falling back to `CONTRACT_TIMEZONE` and then UTC.
  When an operator reports a contract flagged a day early or late, check that tenant's zone before
  suspecting the date arithmetic.
- The `documents` queue is currently **dead**: `worker.py` listens on it, but no job functions are
  registered for it and no backend code enqueues to it. It is reserved for the Phase 5 OCR/embed wave.
- **No backend code calls the worker.** `worker/enqueue.py` and `beat.py` are the only producers;
  there is no `rq_queue.enqueue(...)` anywhere in `backend/app/`. Work the app hands to the worker
  has to go through the HTTP routes the jobs call.
- **Before trusting the dashboard's "expiring" count, check `beat` is running.** The live
  `/contracts?expiring=true` calculation is a live query (B-13), but the *stored* status is still
  written by the roll. If `beat` is down, the roll-dependent surfaces are as fresh as the last
  successful run — `docker compose logs beat` is the thing to read.

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
