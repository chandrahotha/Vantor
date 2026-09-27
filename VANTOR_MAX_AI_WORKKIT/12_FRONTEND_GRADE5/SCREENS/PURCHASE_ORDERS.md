<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../../docs/BRAIN.md) · [Docs index](../../../docs/README.md)

# Purchase Orders Screen Specification

PO list with lifecycle filters, budget/approval/receipt/invoice status. PO detail has line quantities, receipt progress, invoicing progress, commitments, documents, approvals and actions.

## Required content

Use the shared design system. Every screen must expose breadcrumbs, page-level actions, filter/search state, empty/loading/error states, last-updated/freshness where data can be stale, and role-aware actions. Financial actions show currency and consequence before commit.

## Acceptance

The screen is complete only when its primary user journey is covered by browser E2E and visual regression at desktop/tablet/mobile.
