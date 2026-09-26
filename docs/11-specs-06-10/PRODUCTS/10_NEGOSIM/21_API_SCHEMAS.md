# API Schema Examples — AI Supplier Negotiation Simulator

## Request envelope
`{"data": {...}, "meta": {"request_id": "client-generated-or-server-issued", "version": "v1"}}`

## Response envelope
`{"data": {...}, "meta": {"request_id": "...", "version": "v1"}}`

## Error envelope
`{"error": {"code": "STATE_INVALID", "message": "Safe user-facing explanation", "details": {}, "request_id": "..."}}`

## Async job fields
`job_id`, `status`, `requested_at`, `started_at`, `completed_at`, `attempt`, `input_hash`, `result_hash`, `error_code`, `request_id`.

## Idempotency
The API persists the first successful command result keyed by tenant + actor + operation + idempotency key. A replay returns the same durable outcome without duplicating the side effect.
