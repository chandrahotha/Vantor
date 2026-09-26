# API Contract — Procurement Spend Intelligence Agent

All APIs use the inherited envelope:

`{"data": {}, "meta": {"request_id": "...", "version": "v1"}}`

Errors use:

`{"error": {"code": "...", "message": "...", "details": {}, "request_id": "..."}}`

## Core endpoints
- `POST /api/v1/spend-batches`
- `GET /api/v1/spend-batches/{id}`
- `POST /api/v1/spend-batches/{id}/profile`
- `POST /api/v1/spend-batches/{id}/classify`
- `GET /api/v1/spend/cube`
- `GET /api/v1/spend/opportunities`
- `POST /api/v1/spend/reviews/{id}/decide`
- `POST /api/v1/spend/exports`

## Idempotency
Material POST operations accept an idempotency key. The key is scoped to tenant + actor + operation type and maps to a durable command result.

## Events
Use the event names listed in `00_PORTFOLIO_BRAIN/02_CROSS_PRODUCT_INTEGRATION.md` plus product-local events. All events contain event id, tenant id, occurred_at, producer version, schema version and source record id.
