<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Worker — VANTOR

**Status: `IN DEVELOPMENT` — RQ + Redis (canonical queue per audit).**

Jobs never duplicate API rules — they call the API with a service token
(Keycloak client-credentials) or run DBInfra-light maintenance. No fake realtime:
every job result is a real row/audit event.

Queues: `default` (expiry roll, spend rollups), `documents` (Wave 2: OCR/chunk/embed).

## Run

```powershell
pip install -r requirements.txt
python worker.py
# enqueue once:
python enqueue.py roll_expiry
```
