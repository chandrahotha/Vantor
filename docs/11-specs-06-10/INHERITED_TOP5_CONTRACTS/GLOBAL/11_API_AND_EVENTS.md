# API and Event Contracts

REST examples:
GET /api/v1/rfqs
POST /api/v1/rfqs
GET /api/v1/rfqs/{id}
POST /api/v1/rfqs/{id}/documents
POST /api/v1/rfqs/{id}/analyze
GET /api/v1/rfqs/{id}/analysis
POST /api/v1/rfqs/{id}/approve
POST /api/v1/rfqs/{id}/export

Envelope:
{"data": {}, "meta": {"request_id": "...", "version": "v1"}}

Error:
{"error": {"code": "...", "message": "...", "details": {}, "request_id": "..."}}

Async states:
Queued → Validating → Processing → NeedsReview → Complete / Failed.

Events:
document.uploaded
document.extracted
analysis.started
analysis.completed
risk.updated
scenario.created
approval.requested
approval.completed
export.created
security.alert

All async jobs are idempotent.
