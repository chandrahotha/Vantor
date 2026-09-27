<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Webhook Retry

State model: queued -> delivering -> delivered OR retry_scheduled -> dead_letter. Store attempts, next_attempt_at, response status, last error, signature version, event id, idempotency key. Exponential backoff with jitter. Do not sleep inside API requests.
