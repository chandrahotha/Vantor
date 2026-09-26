# Operational Runbook — Strategic Sourcing Optimization Engine

## Routine checks
- API health and error rate
- worker queue depth and dead-letter count
- database connection saturation
- object storage failures
- slow analytical jobs
- AI provider availability (where used)
- integration contract errors
- audit-chain verification failures

## Recovery priorities
1. Prevent new material actions if authorization/audit integrity is degraded.
2. Keep existing durable facts readable.
3. Retry safe idempotent jobs.
4. Route non-retryable jobs to review.
5. Restore from backup only under documented incident control.
6. Re-run release/integrity checks before reopening material actions.

## Public demo reset
Destroy/recreate synthetic records; verify no real integration endpoint is enabled; verify demo banner.
