<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Frontend — VANTOR Web

**Status: `IN DEVELOPMENT` — 19 compiled routes, 107 vitest green across 10 test suites.**

Stack: **Next.js 16 App Router + React 19 + TypeScript 5.9**, Keycloak OIDC (Authorization Code +
PKCE, in-memory tokens only) with instant Demo Workspace fallback, ESLint 9 flat config, design tokens per
`../docs/05-frontend/design-system.md`.

Rules: real API data only (envelope `{data,pagination,error,requestId}`), explicit empty/error
states, no localStorage tokens, no fake sessions, no placeholder charts.

## Run

### Option A: Local Dev & Demo Mode (No Keycloak :8080 Required)

```powershell
npm ci
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"
npm run dev
```

Navigate to `http://localhost:3000` and click **"Explore Demo Workspace"**.
This grants immediate access as a Buyer / Procurement Manager without redirecting to port 8080 or requiring a live Keycloak container.

### Option B: Full Enterprise Stack (Keycloak SSO on :8080)

```powershell
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"
$env:NEXT_PUBLIC_KEYCLOAK_URL="http://localhost:8080"
npm run dev
```

On `http://localhost:3000`, click **"Continue with Vantor ID"** to authenticate via Keycloak OIDC.

## Verification & Gates

```powershell
npm run typecheck    # tsc --noEmit (0 errors)
npm run lint         # eslint (0 errors, 0 warnings)
npm test             # vitest (107/107 passed across 10 suites)
npm run build        # next build (19 routes generated)
```

All four gates pass. CI validates them on push and PR.

## Security & Headers

Security headers are part of the build contract, not an afterthought: `next.config.mjs` sets a
Content-Security-Policy plus `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` and
`Permissions-Policy` on every response from the app. A CSP served by the API governs documents the
*API* serves, so the app needs its own — without it the pages a user reads are unprotected.
`next.config.test.ts` asserts the policy exists, is derived from `NEXT_PUBLIC_API_URL` /
`NEXT_PUBLIC_KEYCLOAK_URL` rather than hardcoded, and that HSTS appears only over https.

## Theming & UI Architecture

Five palettes × light/dark, driven by CSS custom properties under
`[data-palette="<key>"]` and `[data-theme="light|dark"]`, not by hardcoded surface colours.
Selection persists via `useSyncExternalStore` (`lib/palette.ts`) and a tenant's identity-token
brand claim can override it. `check_palette_layer.py` gates the layer: no cycles, no dangling
tokens, and every contrast pair above its threshold.

Shared UI primitives live in `components/ui.tsx`:
- `useBoot`: Unified Keycloak SSO and instant Demo session hydration with bounce-loop detection.
- `AuthScreen`: Executive glassmorphic entry screen with dual SSO / Demo actions.
- `StatCard`, `Pager`, `DataTable`: Standardized data grid with accessible ARIA sort.
- `Badge`, `Empty`, `ErrorBox`, `Skeleton`: Standardized feedback and empty states.
- Fonts: `Inter` and `JetBrains Mono` are bundled via `next/font` in `layout.tsx`.
