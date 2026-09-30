<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../../BRAIN.md) · [Docs index](../../../README.md)

# Receipts Screen Specification

Receipt entry and history with line-level remaining quantity and receiving exceptions. Concurrency-safe feedback.

## Required content

Use the shared design system. Every screen must expose breadcrumbs, page-level actions, filter/search state, empty/loading/error states, last-updated/freshness where data can be stale, and role-aware actions. Financial actions show currency and consequence before commit.

## Acceptance

The screen is complete only when its primary user journey is covered by browser E2E and visual regression at desktop/tablet/mobile.
