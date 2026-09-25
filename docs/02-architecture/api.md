<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# API Architecture — VANTOR

**Status: `PLANNED`. Base: `/api/v1/...`, OpenAPI published from code.**

## Conventions
- REST for CRUD/workflows; webhooks/events for inbound/outbound async; consistent envelope `{data, pagination, error{code,message,details,requestId}}`.
- Versioning via URL; idempotency keys on mutating P2P/AI actions; pagination (`cursor` preferred) + filter/sort/field selection; typed validation errors (422) with field paths.
- Never expose internal columns; map to DTOs; authz checked per resource (role + scope + ownership + spending limit).

## Surface (representative)
`/auth/*, /orgs, /suppliers, /categories, /sourcing-projects, /rfqs, /quotes, /awards, /contracts, /requisitions, /purchase-orders, /receipts, /invoices, /spend, /savings, /approvals, /workflows, /documents, /ai/conversations, /notifications, /integrations, /webhooks, /audit-events`

## AI tools (typed, permission-checked)
`search_suppliers get_supplier compare_suppliers create_rfq get_rfq analyze_quotes compare_quotes analyze_contract get_contract_obligations calculate_savings find_spend_anomalies request_approval get_purchase_orders get_supplier_performance generate_report` — all logged as `AI_TOOL_EXECUTED` with evidence refs.

## Contract source
`api/openapi.yaml` generated at build; breaking changes require migration notes + version bump. Full reference published in Phase 3.
