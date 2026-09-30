<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../BRAIN.md) · [Docs index](../../README.md)

# Frontend State and Error Patterns

Every page must model at least: initial loading, loaded empty, loaded data, partial failure, full failure, mutation pending, mutation success, mutation conflict, validation error, permission denied, stale data and retry.

Financial mutations should use server-confirmed state. Mutation buttons must be disabled while the exact operation is in flight. After success, refresh only the affected query groups or receive server event updates.
