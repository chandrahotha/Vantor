# Integrations Screen Specification

Integration center with adapters, health, secret status, webhook endpoints, delivery queue, retry/DLQ/replay and event trace.

## Required content

Use the shared design system. Every screen must expose breadcrumbs, page-level actions, filter/search state, empty/loading/error states, last-updated/freshness where data can be stale, and role-aware actions. Financial actions show currency and consequence before commit.

## Acceptance

The screen is complete only when its primary user journey is covered by browser E2E and visual regression at desktop/tablet/mobile.
