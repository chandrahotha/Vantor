# Frontend — VANTOR Web

The web application: every procurement workspace, the approvals queue, spend
analytics, contract obligations and an evidence-grounded AI copilot.

**15 routes** in a Next.js 16 App Router application.

**Stack:** Node 22 · Next.js 16 · React 19 · TypeScript 6 · Tailwind-free CSS
custom properties · Keycloak OIDC (Authorization Code + PKCE) · ESLint 10 ·
Vitest 5.

**No demo mode.** Every panel is fed by the API. When the API is unreachable the
UI says so and names the address it tried, rather than falling back to invented
records: a dashboard of plausible fake numbers is indistinguishable from a
working one to the person reading it.

## The routes

| Route | What it is |
|---|---|
| `/` | Dashboard |
| `/suppliers`, `/suppliers/[id]` | Supplier 360 — profile, scorecards, qualifications, performance |
| `/requisitions` | Requisition intake and tracking |
| `/rfqs` | RFQs, quote comparison, award |
| `/contracts` | Contracts, obligations, renewal windows |
| `/orders` | Purchase orders with price check |
| `/spend` | Spend analytics, leakage, concentration, should-cost |
| `/documents` | Document library, upload, search |
| `/approvals` | Approval queue and decisions |
| `/governance` | Policy, budgets, audit |
| `/integrations` | Connected systems and webhook health |
| `/negosim` | AI negotiation simulator |
| `/notifications` | Notification feed |
| `/copilot` | Evidence-grounded AI copilot |

## Run it

```bash
npm ci
NEXT_PUBLIC_API_URL="http://localhost:8000" \
NEXT_PUBLIC_KEYCLOAK_URL="http://localhost:8080" \
npm run dev
```

Open `http://localhost:3000`.

On boot the app renders its own loading state and, if there is no identity
provider session, a sign-in card with a single **Continue with Vantor ID**
button. The window is never redirected to the identity provider without that
click — an automatic redirect is what stranded users when the IdP was
unreachable.

Tokens are held in memory only, never in `localStorage`. There is no
in-app persona switcher, no role picker, and no path to a session that does
not come from the identity provider.

## Verification

```bash
npm run typecheck    # tsc --noEmit
npm run lint         # eslint
npm test             # vitest — 159 vitest green across 13 suites
npm run build        # next build
```

All four gates pass, and CI runs them on every push and pull request.

## Security headers

Security headers are part of the build contract, not an afterthought. The
Next.js config sets a Content-Security-Policy plus `X-Frame-Options`,
`X-Content-Type-Options`, `Referrer-Policy` and `Permissions-Policy` on every
response the app serves. A CSP served by the API governs documents the *API*
serves, so the app needs its own — without it, the pages a user reads are
unprotected.

The policy is derived from `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_KEYCLOAK_URL`
rather than hardcoded, and HSTS appears only over https. A test asserts all
of it.

## Design system

Five palettes × light/dark, driven by CSS custom properties under
`[data-palette="<key>"]` and `[data-theme="light|dark"]` — not by hardcoded
surface colours. The default is **Vantor Cobalt** (Hyper Cobalt `#0038FF` +
Skin Sand `#FFD8B8`).

Selection persists, and a tenant's identity-token brand claim can override
it. A palette audit gates the token layer: no cycles, no dangling tokens, and
every contrast pair above its threshold.

Shared primitives cover stat cards, pagers, data tables with accessible ARIA
sorting, badges, and the empty/error/skeleton states. Typography is bundled
at build time rather than fetched at runtime.

Full reference: [design system](../docs/05-frontend/design-system.md) and
[brand](../docs/06-brand/logo.md).

## Dependency posture

- The whole tree audits clean — `npm audit --audit-level=low` reports **0
  vulnerabilities**, dev dependencies included. The production surface is
  gated separately in CI at `--omit=dev --audit-level=high`.
- **Accepted risk:** `braces ≤ 3.0.3` (GHSA-vfj7-8cjw-p6xm, high,
  stack exhaustion via deeply nested patterns) arrives transitively through
  `eslint-config-next` → `@next/eslint-plugin-next` → `fast-glob` →
  `micromatch`. No patched release exists upstream, so there is nothing to
  upgrade to — and a downgrade does not remove it either. It runs at
  lint/build time over repo-controlled glob patterns, never over
  attacker-controlled input at runtime.
- **`minimatch` is overridden to `^11.0.1`** (GHSA-g3hv-75wg-m249, moderate,
  denial of service via glob-parts amplification). The flaw is in minimatch
  v10's pattern optimizer; minimatch v3 does not contain that code path at
  all, but the advisory's affected range is a blanket `< 11.0.1`, so the
  scanner flags every copy in the tree. Forcing the tree to v11 is what
  closes the alert.
- **That override has one consequence, and it is guarded.** minimatch v3's
  module export was a *callable* function; v11's is an object with a named
  `minimatch` export. `eslint-plugin-import`, `eslint-plugin-react` and
  `eslint-plugin-jsx-a11y` call the module directly, so five of their rules
  (`import/extensions`, `import/no-extraneous-dependencies`,
  `react/no-unstable-nested-components`, `react/forbid-component-props`,
  `react/jsx-pascal-case`) cannot run under v11. None is enabled here and
  `eslint-config-next` does not enable them either. The ESLint config checks
  the composed config and fails with an actionable message if one of them is
  ever switched on, rather than letting it blow up mid-lint.

## Documentation

- [Design system](../docs/05-frontend/design-system.md) ·
  [Brand](../docs/06-brand/logo.md)
- [Security architecture](../docs/04-security/architecture.md) ·
  [Threat model](../docs/04-security/threat-model.md)
- [Deployment reference](../docs/08-deployment/local.md)
- [Full documentation index](../docs/README.md)
