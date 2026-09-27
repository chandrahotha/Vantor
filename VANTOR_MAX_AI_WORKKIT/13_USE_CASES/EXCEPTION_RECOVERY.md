<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Exception Recovery

User hits any partial failure -> sees what committed -> receives requestId -> retries safely via idempotency -> system reconciles downstream effects.

Each journey needs main, alternate and exception flows and automated E2E coverage.
