<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Worker — VANTOR

**Status: RQ + Redis, 4 job functions, 3 of them on a schedule.**
This is the smallest module in the repo and the least finished.

Jobs never duplicate API rules — they call the API with a service token
(Keycloak client-credentials) or run DBInfra-light maintenance. No fake realtime:
every job result is a real row or audit event.

Queues: `default` (expiry roll, spend rollups, webhook drain), `documents`
(reserved for the Phase 5 OCR/chunk/embed wave).

## Scheduling: `beat.py`, one mechanism

`beat.py` is a compose service in its own right, so Ops can see the scheduler and
the workers independently. It is the *only* scheduler in the stack — there is no
system crontab and no second enqueuer, so a job has exactly one path to being
queued.

| Job | Default interval | Env override |
|---|---|---|
| `roll_expiry` | daily | `ROLL_EXPIRY_INTERVAL_S` |
| `drain_webhooks` | every 30s | `WEBHOOK_DRAIN_INTERVAL_S` |
| `spend_snapshot` | hourly | `SPEND_SNAPSHOT_INTERVAL_S` |

A non-positive or unparseable override falls back to the default rather than
becoming a tight loop against the database.

It is written against the **pinned** rq 1.16.2, whose actual surface is
`RQScheduler(queues, connection, interval=...)` plus `work()` /
`enqueue_scheduled_jobs()`. The previous version called
`RQScheduler(queue_name=...)` and `scheduler.schedule(...)` — neither exists in
that version, so the service died on boot and no recurring job had ever run
(B-34).

Because rq 1.16.2's `Queue.enqueue` has no `repeat` parameter, a recurring job
cannot be declared once and forgotten. `BeatScheduler` re-arms each schedule on
every scheduler tick, inside the same loop that promotes due jobs, so there is
one process and one lifecycle rather than a second heartbeat that could die and
leave the schedule silently decaying. The unit tests in `worker/tests/` cover
this with a fake queue and registry — no Redis required.

**No duplicate work.** Job ids are `beat:<name>:<bucket>`, where the bucket is
the absolute epoch-time interval, not a counter. Re-arming the same bucket is a
no-op in Redis, so restarting `beat` — or running a second instance — never
queues a second copy of a job that is already pending. Because the grid is
absolute, a scheduler that was down for an hour re-arms onto the existing
schedule instead of shifting every future run by the length of the outage.

Each job is also idempotent on the API side: `roll_expiry` is a date-derived
state transition, `spend_snapshot` is a read, and `drain_webhooks` claims due
deliveries from a durable queue whose retry schedule lives in the database.

## Identity: a machine role, not an administrator

The worker authenticates with client credentials for the `vantor-service` client
and is granted exactly one realm role, `Service Identity`. That role is granted to
no human and is deliberately **not** a subset of any human role, so a leaked
worker secret cannot reach anything a person could.

It covers precisely the two operations the worker performs:

| Operation | Endpoint | Why this role is enough |
|---|---|---|
| Contract expiry roll | `POST /contracts/expire-roll` | Moves `active` → `expiring` on date-derived state. No money moves. |
| Webhook delivery drain | `POST /integrations/webhooks/drain` | Sends queued payloads to the tenant's own registered endpoints. |

It deliberately cannot activate, terminate, sign, review or renew a contract, nor
approve a requisition. `tests/test_realm_parity.py` asserts the grant is exactly
one role, that no human role set includes it, that both operations are still
reachable, and that the administrative ones are refused.

This replaced a grant of `Super Admin` + `Procurement Admin` + `Procurement
Manager`, which existed only because the expiry roll required `Super Admin`. The
secret behind those grants lives in the environment of two containers, so a leaked
environment was a fully administrative token.

## Known limitation: the worker drains one tenant

The worker's delivery loop goes through the tenant-scoped HTTP route, so it drains
the tenant its own token belongs to. In a genuinely multi-tenant deployment a
single worker will not deliver the other tenants' webhooks. This is a limit of the
worker's design, not a leak — and it is deliberately *not* papered over by giving
the worker a cross-tenant scope, which would undo the least privilege above. A
cross-tenant drain needs its own explicitly cross-tenant identity and entry point.

The same applies to the expiry roll, which is a per-tenant date computation.

## Run

```powershell
pip install -r requirements.txt pytest
python worker.py      # consumes default + documents
python beat.py        # the scheduler
pytest tests -q       # scheduler tests, no Redis needed
python enqueue.py roll_expiry   # run one job now, by hand
```

## What is NOT here (do not assume it)

- **The `documents` queue is dead.** `worker.py` listens on it, but no job functions are
  registered for it and no backend code enqueues to it.
- **No backend code enqueues to RQ.** `worker/enqueue.py` and `beat.py` are the only
  producers; there is no `rq_queue.enqueue(...)` anywhere in `backend/app/`. Work that
  the app hands to the worker has to go through the HTTP routes the jobs call.
- **`sweep_idempotency_claims` is not scheduled.** It is reachable from
  `enqueue.py` but is a deliberate no-op, because claim expiry is enforced inline by the
  middleware.
- **A single worker can overlap itself on the 30s drain.** The schedule is drift-free but
  not exclusive: if a drain run takes longer than its interval, the next one is armed
  while the previous is still going. This is harmless because the drain is idempotent, but
  it is a property of the design, not something the scheduler prevents.
- **The scheduler is verified against a fake, not against a live Redis.** The tests prove
  the rq API surface and the arming/idempotency logic; actual promotion of a due job is
  RQ's own behaviour and is only proven where a real Redis runs.
- The `Service Identity` role now exists in the realm export and `deploy/keycloak/provision.py`
  grants it to the `vantor-service` client, but **you still have to run the provisioner** to
  have it in a live realm. The `enqueue.py` service token is only issued by the local
  Keycloak realm if `deploy/keycloak/provision.py` has been run against it.
