<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Frontend — VANTOR Web

**Status: `IN DEVELOPMENT` — Phase 7 Wave 1 (dashboard + suppliers + RFQs + contracts + orders + spend + documents + copilot).**

Stack: **Next.js 14 App Router + React 18 + TypeScript**, Keycloak OIDC (Authorization Code + PKCE, in-memory tokens only), design tokens per `../docs/05-frontend/design-system.md`.

Rules: real API data only (envelope `{data,pagination,error,requestId}`), explicit empty/error states, no localStorage tokens, no fake sessions, no placeholder charts.

## Run

```powershell
Copy-Item ..\..\\.env.example ..\..\\.env
npm install
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"
$env:NEXT_PUBLIC_KEYCLOAK_URL="http://localhost:8080"
npm run dev
npm run typecheck
npm run build
```

> `NEXT_PUBLIC_*` values are baked at build time — rebuild (or `docker compose build
> frontend`) after changing them. CI builds with the localhost test values above.
