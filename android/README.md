<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [Brain](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Android - VANTOR (Phase 9) - NOT STARTED

**Status: `PLANNED`. There is deliberately no code here yet.**

A native Android client arrives after Phase 10 hardening. When it starts, it targets the
same backend the web app already uses:

- **Auth:** Keycloak OIDC Authorization Code + PKCE (same `vantor-web` client shape; a mobile
  client ``android`` will be registered with the mobile redirect).
- **First screens (approved baseline):** approvals inbox, alerts feed, PO detail, order
  receipts, supplier lookup. Anything else needs its own phase ticket.
- **Do not commit secrets.** The app reads its config from the device keystore at runtime.
- **Everything below ships through the API** (/api/v1) with real persistence - a mock-first
  approach is not accepted.

When work starts, the first review will require: a runnable debug APK, on-device
login → list → approve → decision round-trip, and a screen recording linked in the PR.
