<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Android Strategy - VANTOR

**Status: `PLANNED` (Phase 9). API-first: same `/api/v1` backend, no second backend.**

## Scope (mobile-first = approvals-first)
Approvals, alerts (contract expiry, risk, RFQ updates), purchase requests, supplier lookup, RFQ status, contract alerts, Copilot assistant, document viewing.

## Stack
Kotlin, Jetpack Compose, Clean Architecture + MVVM, Retrofit/OkHttp +kotlinx.serialization, DataStore, WorkManager (offline queue), FCM push, App Links deep-links (`vantor://approvals/{id}`), BiometricPrompt gate for high-risk approvals, CameraX (doc capture) → same document pipeline.

## Auth/offline
OIDC (Keycloak) via AppAuth, short access + rotated refresh in EncryptedSharedPreferences/Keystore. Offline-aware: cached queues/dashboards, outbox-pattern approval intents with idempotency keys, conflict resolution server-side. Every mobile action hits typed tools → same HITL + audit as web.

## Gates
Auth + approve-PO E2E on device, push round-trip, offline-queue replay tests. See Brain → `../02-architecture/api.md`, `../04-security/architecture.md`, `../03-ai/architecture.md`.
