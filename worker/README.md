<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Worker — VANTOR

**Status: `IN DEVELOPMENT` — RQ + Redis, 2 job functions, nothing scheduled yet.**
This is the smallest module in the repo and the least finished.

Jobs never duplicate API rules — they call the API with a service token
(Keycloak client-credentials) or run DBInfra-light maintenance. No fake realtime:
every job result is a real row or audit event.

Queues: `default` (expiry roll, spend rollups), `documents` (reserved for the Phase 5
OCR/chunk/embed wave).

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
pip install -r requirements.txt
python worker.py
python enqueue.py roll_expiry
```

## What is NOT here (do not assume it)

- **Nothing schedules these jobs.** There is no beat/cron sidecar in `docker-compose.yml` and no
  periodic enqueue. `roll_expiry` and `spend_snapshot` only run when a human runs `enqueue.py`.
  So contract expiry rolling and spend rollups are **not** running in any environment, including
  the local compose stack.
- **The `documents` queue is dead.** `worker.py` listens on it, but no job functions are
  registered for it and no backend code enqueues to it.
- **No backend code calls the worker.** `worker/enqueue.py` is a manual CLI; there is no
  `rq_queue.enqueue(...)` anywhere in `backend/app/`. Asynchronous work does not exist yet.
- The `Service Identity` role now exists in the realm export and `deploy/keycloak/provision.py`
  grants it to the `vantor-service` client, but **you still have to run the provisioner** to
  have it in a live realm. The `enqueue.py` service token is only issued by the local
  Keycloak realm if `deploy/keycloak/provision.py` has been run against it.
