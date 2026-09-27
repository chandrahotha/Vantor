# Exception Recovery

User hits any partial failure -> sees what committed -> receives requestId -> retries safely via idempotency -> system reconciles downstream effects.

Each journey needs main, alternate and exception flows and automated E2E coverage.
