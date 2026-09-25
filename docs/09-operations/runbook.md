<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Operations Runbook — VANTOR

**Status: `PLANNED`.**

## Health
`GET /api/v1/health` (liveness), `/ready` (DB+Redis+storage checks). Dashboards: API latency/error rate, queue depth, worker lag, doc-pipeline states, AI latency/tokens/cost, integration failures.

## Backups
Nightly Postgres dump + WAL/PITR (managed in prod); MinIO versioning + cross-region copy; Keycloak realm export. Quarterly restore drill with signed record.

## Incidents
Sev1 (data leak/tenant breach/financial mis-post) → freeze deploys, preserve audit, rotate keys, notify. AI incident (hallucinated award/injection) → disable tool per `../03-ai/safety.md`, keep `AI_TOOL_EXECUTED` trail, post-mortem ADR.

## On-call basics
Logs structured JSON with `tenant_id, request_id, actor`; alerts on error-rate/latency/queue-depth/expiry-miss; runbook links from every alert. See Brain → `../08-deployment/local.md`, `../04-security/threat-model.md`.
