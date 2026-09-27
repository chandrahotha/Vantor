<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Frontend — VANTOR Web

**Status: `IN DEVELOPMENT` — 15 routes, 99 vitest green.**

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
`build` (next build). All three must pass; CI runs all three plus the container build.

## What is NOT here (do not assume it)

- **Every write path is API-only.** RFQ create/quote/award, PO approve/send/receipt/invoice,
  catalog, budgets, integrations, the audit viewer, document extract/search and the HITL decision
  endpoint have no UI. The product is currently read-heavy in the browser by design.
- **Zero frontend tests.** No runner is configured. `docs/00-plan/ROADMAP.md` Phase 7's a11y and
  perf gate cannot be met until one exists.
- **No dark mode.** `globals.css` hardcodes light surfaces; there is no `prefers-color-scheme`
  block and no theme token indirection.
- **The declared fonts are not shipped.** `--font-ui: Inter` / `--font-mono: JetBrains Mono` have
  no `@font-face`, no `next/font` and no webfont file, so both fall back to system fonts.
- **No shared table/pager/card primitives.** The cursor pager is written 4×, the Keycloak boot 5×
  and the raw grid 9×. This is the main obstacle to adding write paths safely.
- **`next.config.mjs` inlines `NEXT_PUBLIC_*` at build time**, so the compose `env_file` cannot
  change them for the browser bundle.
- **`public/logo.svg` is the Digi Tracks company mark**, not the VANTOR identity set in
  `assets/brand/`, and it is used for both `openGraph.images` and `icons.icon`.
