<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Worker — VANTOR

**Status: `IN DEVELOPMENT` — RQ + Redis, 2 job functions, nothing scheduled yet.**
This is the smallest module in the repo (52 lines) and the least finished.

Jobs never duplicate API rules — they call the API with a service token
(Keycloak client-credentials) or run DBInfra-light maintenance. No fake realtime:
every job result is a real row or audit event.

Queues: `default` (expiry roll, spend rollups), `documents` (reserved for the Phase 5
OCR/chunk/embed wave).

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
- `enqueue.py` needs a service token that is not issued by the local Keycloak realm yet.
