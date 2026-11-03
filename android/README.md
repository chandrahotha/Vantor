# Android — VANTOR

**Status: not started. There is deliberately no code here yet.**

A native Android client is planned. When it starts, it targets the same
backend the web app already uses — `/api/v1` is the contract, and it is
already built for a mobile client.

## What it will use

- **Auth:** Keycloak OIDC Authorization Code + PKCE, the same shape as the
  web app, with a separate mobile client registered and a mobile redirect.
- **First screens:** approvals inbox, notifications feed, purchase-order
  detail, order receipts, supplier lookup.
- **Config:** read from the device keystore at runtime. Secrets are never
  committed.
- **Data:** everything ships through the API with real persistence. A
  mock-first approach is not acceptable here.

## What has to be true before it lands

A first review of the client will require a runnable debug APK, an on-device
login → list → approve → decision round trip, and a screen recording linked
from the pull request.

## Documentation

- [Android strategy](../docs/07-android/strategy.md)
- [API design](../docs/02-architecture/api.md)
- [Full documentation index](../docs/README.md)
