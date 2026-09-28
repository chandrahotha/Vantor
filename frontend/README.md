<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Frontend — VANTOR Web

**Status: `IN DEVELOPMENT` — 15 routes, 106 vitest green.**

Stack: **Next.js 16 App Router + React 19 + TypeScript 5.9**, Keycloak OIDC (Authorization Code +
PKCE, in-memory tokens only), ESLint 9 flat config, design tokens per
`../docs/05-frontend/design-system.md`.

Rules: real API data only (envelope `{data,pagination,error,requestId}`), explicit empty/error
states, no localStorage tokens, no fake sessions, no placeholder charts.

## Run

```powershell
npm ci
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"
$env:NEXT_PUBLIC_KEYCLOAK_URL="http://localhost:8080"
npm run dev
npm run typecheck
npm run lint
npm run build
```

> `NEXT_PUBLIC_*` values are baked at build time — rebuild (or `docker compose build frontend`)
> after changing them. CI builds with the localhost test values.

## Gates

`typecheck` (tsc --noEmit) · `lint` (eslint, `next/core-web-vitals` + `next/typescript`) ·
`test` (vitest) · `build` (next build). All four must pass; CI runs them plus the container build.

Security headers are part of the build contract, not an afterthought: `next.config.mjs` sets a
Content-Security-Policy plus `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` and
`Permissions-Policy` on every response from the app. A CSP served by the API governs documents the
*API* serves, so the app needs its own — without it the pages a user reads are unprotected.
`next.config.test.ts` asserts the policy exists, is derived from `NEXT_PUBLIC_API_URL` /
`NEXT_PUBLIC_KEYCLOAK_URL` rather than hardcoded, and that HSTS appears only over https.

## Theming

Five palettes × light/dark, driven by CSS custom properties under
`[data-palette="<key>"]` and `[data-theme="light|dark"]`, not by hardcoded surface colours.
Selection persists via `useSyncExternalStore` (`lib/palette.ts`) and a tenant's identity-token
brand claim can override it. `check_palette_layer.py` gates the layer: no cycles, no dangling
tokens, and every contrast pair above its threshold. Rationale, including why there is no
Tailwind/Zustand layer, is in `../docs/05-frontend/theming-layer-migration.md`.

## What is NOT here (do not assume it)

- **Every write path is API-only.** RFQ create/quote/award, PO approve/send/receipt/invoice,
  catalog, budgets, integrations, the audit viewer, document extract/search and the HITL decision
  endpoint have no UI. The product is currently read-heavy in the browser by design.
- **No browser-level tests.** The 106 vitest tests are unit and component level, run in jsdom —
  there is no Playwright, so no real end-to-end journey, no automated accessibility audit and no
  visual regression. `docs/00-plan/ROADMAP.md` Phase 7's a11y and perf gate cannot be met until a
  browser runner exists. The palette layer's contrast is checked by `check_palette_layer.py`
  instead, which is a static check and not a substitute.
- **The declared fonts are not shipped.** `--font-ui: Inter` / `--font-mono: JetBrains Mono` have
  no `@font-face`, no `next/font` and no webfont file, so both fall back to system fonts.
- **No shared table/pager/card primitives.** The cursor pager is written 4×, the Keycloak boot 5×
  and the raw grid 9×. This is the main obstacle to adding write paths safely.
- **`next.config.mjs` inlines `NEXT_PUBLIC_*` at build time**, so the compose `env_file` cannot
  change them for the browser bundle.
- **`public/logo.svg` is the Digi Tracks company mark**, not the VANTOR identity set in
  `assets/brand/`, and it is used for both `openGraph.images` and `icons.icon`.
