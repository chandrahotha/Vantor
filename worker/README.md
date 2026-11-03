# Worker — VANTOR

The background worker: a Redis queue consumer and the scheduler that feeds
it. It is the smallest module in the repository and does the least — on
purpose.

**Stack:** Python 3.14 · RQ 3 · Redis 8 · httpx.

Jobs never duplicate API rules. They call the API with a service token, or
run a small amount of database maintenance. Every job result is a real row
or a real audit event — there is no fake realtime and no synthetic success.

**Queues:** `default` (expiry roll, spend snapshots, webhook drain) and
`documents` (reserved for OCR, chunking and embedding work).

## Scheduling

The scheduler is a service in its own right, so operations can see the
scheduler and the workers independently. It is the *only* scheduler in the
stack — no system crontab, no second enqueuer — so a job has exactly one
path to being queued.

| Job | Default interval | Override |
|---|---|---|
| `roll_expiry` | daily | `ROLL_EXPIRY_INTERVAL_S` |
| `drain_webhooks` | every 30s | `WEBHOOK_DRAIN_INTERVAL_S` |
| `spend_snapshot` | hourly | `SPEND_SNAPSHOT_INTERVAL_S` |

A non-positive or unparseable override falls back to the default rather than
becoming a tight loop against the database.

**No duplicate work.** Job ids are `beat:<name>:<bucket>`, where the bucket is
an absolute time interval rather than a counter. Re-arming the same bucket is
a no-op in Redis, so restarting the scheduler — or running a second instance
— never queues a second copy of a job that is already pending. Because the
grid is absolute, a scheduler that was down for an hour re-arms onto the
existing schedule instead of shifting every future run by the length of the
outage.

Each job is also idempotent on the API side: `roll_expiry` is a date-derived
state transition, `spend_snapshot` is a read, and `drain_webhooks` claims due
deliveries from a durable queue whose retry schedule lives in the database.

## Identity

The worker authenticates with client credentials and holds exactly one realm
role — a service role that is granted to no human and is deliberately **not**
a subset of any human role. A leaked worker secret therefore cannot reach
anything a person could.

It covers precisely the two operations the worker performs:

| Operation | Endpoint | Why this role is enough |
|---|---|---|
| Contract expiry roll | `POST /contracts/expire-roll` | Moves `active` → `expiring` on a date-derived state. No money moves. |
| Webhook delivery drain | `POST /integrations/webhooks/drain` | Sends queued payloads to the tenant's own registered endpoints. |

It deliberately cannot activate, terminate, sign, review or renew a contract,
nor approve a requisition. A test asserts the grant is exactly one role, that
no human role set includes it, that both permitted operations are still
reachable, and that the administrative ones are refused.

## Run it

```bash
pip install -r requirements.txt pytest

python worker.py      # consumes the default and documents queues
python beat.py        # the scheduler
pytest tests -q       # scheduler tests, no Redis needed

python enqueue.py roll_expiry   # run one job now, by hand
```

The scheduler's behaviour is unit-tested against a fake queue and registry, so
the suite runs without a Redis server.

## Current limitations

- **The worker drains one tenant.** Its delivery loop goes through the
  tenant-scoped HTTP route, so it drains the tenant its own token belongs to.
  In a multi-tenant deployment a single worker will not deliver the other
  tenants' webhooks. The same applies to the expiry roll, which is a
  per-tenant date computation.
  This is a limit of the design, not a leak — it is deliberately not papered
  over by giving the worker a cross-tenant scope, which would undo the least
  privilege above. A cross-tenant drain needs its own explicitly
  cross-tenant identity and entry point.
- **The `documents` queue is empty.** The worker listens on it, but no job
  functions are registered for it and nothing enqueues to it yet.
- **No backend code enqueues to RQ.** The scheduler and the manual enqueue
  script are the only producers. Work the app hands to the worker goes
  through the HTTP routes the jobs call.
- **Claim sweeping is not scheduled.** `sweep_idempotency_claims` is
  reachable by hand but is a deliberate no-op, because claim expiry is
  enforced inline by the request middleware.
- **A single worker can overlap itself on the 30-second drain.** The schedule
  is drift-free but not exclusive: if a drain run takes longer than its
  interval, the next one is armed while the previous is still going. This is
  harmless because the drain is idempotent, but it is a property of the
  design rather than something the scheduler prevents.
- **The scheduler is verified against a fake, not against a live Redis.** The
  tests prove the RQ API surface and the arming and idempotency logic;
  actual promotion of a due job is RQ's own behaviour and is only proven
  where a real Redis runs.
- **The service role must be provisioned.** The role exists in the realm
  export and the provisioner grants it to the service client, but you still
  have to run the provisioner against a live realm before the worker can
  authenticate.

## Documentation

- [Operations runbook](../docs/09-operations/runbook.md) ·
  [Deployment reference](../docs/08-deployment/local.md)
- [Security architecture](../docs/04-security/architecture.md)
- [Full documentation index](../docs/README.md)
