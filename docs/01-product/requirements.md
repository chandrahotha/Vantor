<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Product Requirements — VANTOR

**Status: `PLANNED`. Tagline: Value. Intelligence. Control.**

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

## 5. Internationalization & quality
Multi-currency/timezone/date/tax; no hard-coded INR/USD in logic; validation/normalization/dedupe (supplier, currency, units, categories) + provenance; a11y (keyboard, ARIA, contrast, reduced-motion); perf budgets (fast load, paginated grids, async docs, debounced search, streaming AI).
