# API Contract — Supplier Onboarding & Qualification Agent

All APIs use the inherited envelope:

`{"data": {}, "meta": {"request_id": "...", "version": "v1"}}`

Errors use:

`{"error": {"code": "...", "message": "...", "details": {}, "request_id": "..."}}`

## Core endpoints
- `POST /api/v1/onboarding-cases`
- `POST /api/v1/onboarding-cases/{id}/documents`
- `POST /api/v1/onboarding-cases/{id}/extract`
- `GET /api/v1/onboarding-cases/{id}/checklist`
- `POST /api/v1/checklist-items/{id}/confirm`
- `POST /api/v1/onboarding-cases/{id}/approve`
- `POST /api/v1/onboarding-cases/{id}/export`

## Idempotency
Material POST operations accept an idempotency key. The key is scoped to tenant + actor + operation type and maps to a durable command result.

## Events
Use the event names listed in `00_PORTFOLIO_BRAIN/02_CROSS_PRODUCT_INTEGRATION.md` plus product-local events. All events contain event id, tenant id, occurred_at, producer version, schema version and source record id.
