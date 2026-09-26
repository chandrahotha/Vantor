<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Product Requirements — VANTOR

**Status: `IN DEVELOPMENT`. Tagline: Value. Intelligence. Control.**

**Scope: 10 products.** The canonical product → module → status table is
[`portfolio.md`](portfolio.md). This document states the requirements those products must meet;
it does not restate how many there are.

## 1. Users & roles
Super Admin, Org Admin, Procurement Admin/Manager, Buyer, Category/Supplier Manager, Finance/Legal Reviewer, Approver, Auditor, Supplier User, Read-Only. Configurable permissions + spending limits + approval authority (see security arch).

## 2. Modules (must all work through real backend — no fakes per §2)

- **Supplier intelligence:** discovery, profiles, onboarding, qualification, verification, risk, scorecards, performance, certs, geo/capability/capacity/lead-time, documents, history.
- **Strategic sourcing:** projects, RFI/RFQ/RFP, requirements, invitations, responses, quote collection/normalization/comparison, bid analysis, criteria, events, negotiation, award recommendation.
- **Contract intelligence:** repository, upload (PDF/DOCX/XLSX/CSV/images/scans), OCR, extraction (clauses/obligations/terms), classification, comparison, renewal/expiry alerts, risk + policy-deviation detection.
- **Cost intelligence:** spend by category/supplier/BU, price variance, leakage, maverick spend, savings (negotiated/realized), consolidation + benchmark opportunities.
- **Procurement operations:** requisitions, POs, approvals, workflows, invoices, receiving, exceptions, policies, matrices, notifications.
- **Procurement AI:** copilot, supplier research, RFQ/quote/contract/spend analysis, anomaly detection, recommendations, NL querying, report generation — all evidence-cited with human review gates.

## 3. Procurement Graph
`Supplier→Category→Product/Service→Requirement→RFQ/RFP→Response→Quote→Negotiation→Award→Contract→Requisition→PO→Receipt→Invoice→Spend→Performance→Risk→Savings`. Every entity links to neighbors (e.g., Supplier→Contracts→RFQs→Quotes→POs→Invoices→Spend→Risk).

## 4. Non-negotiables
No fake dashboards/charts/AI/auth/integrations; no hard-coded suppliers; no static-JSON-as-backend; no "coming soon" sold as done; missing external creds → clean interface + explicit config docs, never faked as live.

**Non-negotiables added after the 2026-09-26 audit:**

- **A number in a document is a claim, and claims must be regenerable.** Test counts, route counts
  and framework versions in docs must come from the code, not from memory. CI fails on OpenAPI
  drift; the same discipline applies to prose.
- **A green badge must mean the suite actually ran.** A collection-time error that yields zero
  tests must fail loudly, never render as "N passing".
- **A security control that the test environment cannot exercise must be tested structurally.**
  SQLite has no RLS, so tenant-pinning is asserted by scanning for unpinned sessions, not by
  hoping a query fails.
- **A partial feature states its missing stages in the same sentence as its present ones.**
  "Document pipeline" is not a claim; "validate/store/extract/chunk work, OCR/embed/analyze/
  evidence/review do not" is.

## 5. Internationalization & quality
Multi-currency/timezone/date/tax; no hard-coded INR/USD in logic; validation/normalization/dedupe (supplier, currency, units, categories) + provenance; a11y (keyboard, ARIA, contrast, reduced-motion); perf budgets (fast load, paginated grids, async docs, debounced search, streaming AI).

**Currency rule, stated because it was violated in the UI:** a total aggregated across suppliers
must not be formatted with one arbitrary supplier's currency. Either group by currency or label
the aggregate as currency-agnostic.

## 6. Current state against these requirements

Honest summary — see `../00-plan/ROADMAP.md` for the per-phase breakdown.

| Requirement group | State |
|---|---|
| §2 supplier, sourcing, contract, cost, operations modules | `TESTED` via the API |
| §2 procurement AI | `IN DEVELOPMENT` — typed tools + HITL real; streaming overstated, evidence always empty |
| §2 document intelligence (OCR/extract/classify) | `IN DEVELOPMENT` — ~30%; no OCR, embed, or semantic search |
| §2 notifications | `TESTED` — per-recipient read state, polling delivery |
| §3 procurement graph | `TESTED` in the data model; not surfaced as a UI graph |
| §4 non-negotiables | `TESTED` for API paths; **violated in the UI** (see `../05-frontend/design-system.md` gaps) |
| §5 i18n / multi-currency | `IN DEVELOPMENT` — money math is correct, dashboard aggregation is not |
| §5 a11y | `IN DEVELOPMENT` — focus ring, skip link, ARIA roles present; no focus trap in the palette, no `aria-live`, no route-change focus management |
| §5 perf budgets | `NOT MET` — no frontend test runner, no budget enforcement |
