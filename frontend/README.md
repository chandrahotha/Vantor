<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Frontend - VANTOR Web

🚀 **Live Interactive Deployment:** [VANTOR - Intelligent Procurement Operating System](https://vantor-os.vercel.app/)

**Status: `IN DEVELOPMENT` - 15 routes, 166 vitest green across 13 test suites.**

Stack: **Next.js 16 App Router + React 19 + TypeScript 5.9**, Keycloak OIDC (Authorization Code + PKCE), ESLint 9 flat config, design tokens per `../docs/05-frontend/design-system.md`.

Rules: real API data only (envelope `{data,pagination,error,requestId}`), explicit empty/error
states, no localStorage token leaks, no fake sessions, no placeholder charts.

Features an automated standalone Demo Mode: visitors to [VANTOR - Intelligent Procurement Operating System](https://vantor-os.vercel.app/) can explore every procurement workspace, approvals queue, spend cube, contract obligations, and AI copilot offline without a backend running.

## Run

### Local Development

```powershell
npm ci
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"
$env:NEXT_PUBLIC_KEYCLOAK_URL="http://localhost:8080"
npm run dev
```

Navigate to `http://localhost:3000`. Boot is `check-sso`: the app paints its own loading
splash, and if there is no IdP session it renders a sign-in card with one **Continue with
Vantor ID** button. The window is never navigated to the identity provider without that
click - an automatic redirect is what stranded users on `:8080` when it was down (B-28).

There is no in-app persona switcher, no role picker, and no path to a session that does not
come from the IdP. `lib/auth.ts` holds tokens in memory only, and `components/ui.tsx` renders
`AuthScreen` for every unsigned-in state. Sign-in is Keycloak; sign-out is `kc.logout()`.

## Verification & Gates

```powershell
npm run typecheck    # tsc --noEmit (0 errors)
npm run lint         # eslint (0 errors, 0 warnings)
npm test             # vitest (166 passed across 13 suites)
npm run build        # next build (15 routes generated)
```

All four gates pass. CI validates them on push and PR.

## Security & Headers

Security headers are part of the build contract, not an afterthought: `next.config.mjs` sets a
Content-Security-Policy plus `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` and
`Permissions-Policy` on every response from the app. A CSP served by the API governs documents the
*API* serves, so the app needs its own - without it the pages a user reads are unprotected.
`next.config.test.ts` asserts the policy exists, is derived from `NEXT_PUBLIC_API_URL` /
`NEXT_PUBLIC_KEYCLOAK_URL` rather than hardcoded, and that HSTS appears only over https.

## Dependency audit posture

- Production dependencies audit clean (`npm audit --omit=dev --audit-level=high`,
  CI-gated). Dev-only findings are tracked via Dependabot.
- The **whole** tree audits clean — `npm audit --audit-level=low` reports 0
  vulnerabilities, dev included. `braces` is the one remaining exception, and
  it is an accepted risk rather than a finding (below).
- **Known accepted risk:** `braces ≤ 3.0.3` (GHSA-vfj7-8cjw-p6xm, high,
  stack-exhaustion via deeply nested patterns) arrives transitively through
  `eslint-config-next` → `@next/eslint-plugin-next` → `fast-glob` →
  `micromatch`. No patched release exists upstream, so there is nothing to
  upgrade to — and a downgrade does not remove it either. It runs at
  lint/build time over repo-controlled glob patterns, never over
  attacker-controlled input at runtime. Revisit when upstream ships a fix.
- **`minimatch` is overridden to `^11.0.1`** (GHSA-g3hv-75wg-m249, moderate,
  denial of service via glob-parts amplification in `firstPhasePreProcess()`).
  The flaw is in minimatch v10's pattern optimizer — minimatch v3 does not
  contain that code path at all — but the advisory's affected range is a
  blanket `< 11.0.1`, so the scanner flags every copy in the tree, including
  the v3 ones under `eslint-plugin-import`, `eslint-plugin-react` and
  `eslint-plugin-jsx-a11y`. Forcing the whole tree to v11 is what closes the
  alert and takes `npm audit` to **0 vulnerabilities across dev and prod**.
- **The `minimatch` override has one consequence, and it is guarded.**
  minimatch v3's module export was a *callable* function; v11's is an object
  with a named `minimatch` export. Those three ESLint plugins call the module
  directly, so five of their rules (`import/extensions`,
  `import/no-extraneous-dependencies`, `react/no-unstable-nested-components`,
  `react/forbid-component-props`, `react/jsx-pascal-case`) throw
  `TypeError: minimatch is not a function` under v11. None is enabled here and
  `eslint-config-next` does not enable them either — they are opt-in rules
  inside those plugins, and they only reach minimatch when a glob pattern is
  configured for them. `eslint.config.mjs` checks the composed config and
  fails with an actionable message if one of them is ever switched on, rather
  than letting it blow up mid-lint. Revisit when the upstream plugins migrate
  to minimatch's named export.

## Theming & UI Architecture

Five palettes × light/dark, driven by CSS custom properties under
`[data-palette="<key>"]` and `[data-theme="light|dark"]`, not by hardcoded surface colours.
The default is **Vantor Cobalt** - Hyper Cobalt `#0038FF` + Skin Sand `#FFD8B8`
(`../docs/05-frontend/design-system.md`). The sidebar is the brand anchor: cobalt in every
palette and both modes, white labels and icons, and the active route in Skin Sand with cobalt
text.
Selection persists via `useSyncExternalStore` (`lib/palette.ts`) and a tenant's identity-token
brand claim can override it. `check_palette_layer.py` gates the layer: no cycles, no dangling
tokens, and every contrast pair above its threshold.

Shared UI primitives live in `components/ui.tsx` and `components/Shell.tsx`:
- `useBoot`: Keycloak session boot with bounce-loop detection; `loading` → `ok` → `error` → sign-in.
- `AuthScreen`: the only unauthenticated surface - one explicit sign-in button, a retry on
  IdP failure, and no way to reach the app without a token.
- `StatCard`, `Pager`, `DataTable`: Standardized data grid with accessible ARIA sort.
- `Badge`, `Empty`, `ErrorBox`, `Skeleton`: Standardized feedback and empty states.
- Fonts: `Inter` and `JetBrains Mono` are bundled via `next/font` in `layout.tsx` and applied
  to `<html>`; `--font-ui` / `--font-mono` in `globals.css` reference the variables
  `next/font` emits, with a system stack behind them. `components/grade5.test.tsx` asserts
  both directions, because a token that names a font the build does not ship (B-24) and a
  webfont that is downloaded but never rendered are the same defect.
