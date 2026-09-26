# Error and Failure Model

Standard error classes:

`VALIDATION_ERROR`, `AUTH_REQUIRED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `STATE_INVALID`, `EVIDENCE_MISSING`, `CONTRACT_MISMATCH`, `NORMALIZATION_ERROR`, `SOLVER_INFEASIBLE`, `SOLVER_TIMEOUT`, `AI_UNAVAILABLE`, `AI_SCHEMA_INVALID`, `INGEST_SCAN_FAILED`, `EXPORT_FAILED`, `INTEGRATION_UNAVAILABLE`, `RATE_LIMITED`, `INTERNAL_ERROR`.

Every error exposes a safe code/message plus request id; internal stack traces never reach end users.

Retryable async failures use exponential backoff with bounded attempts and idempotency keys. Non-retryable data-quality failures move the job into a review state. Material actions are never silently retried without an idempotency guard.
