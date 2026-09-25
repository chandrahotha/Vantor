<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ADR-006 — Next.js frontend, API-first for Android

- Context: premium enterprise UI now, Kotlin/Compose app later, one backend.
- Decision: Next.js web on design tokens (`../05-frontend/design-system.md`); all mobile needs served by `/api/v1`; Android Phase 9 per `../07-android/strategy.md`.
- Alternatives: Flutter cross-platform, native-first.
- Consequences: +one API contract; −web must keep API mobile-sufficient (contract tests enforce).
