<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# UI theming layer — migration note

Five enterprise colour palettes with light and dark variants, added to VANTOR as
a token layer. **No feature, layout, module, API, worker, test or business logic
was changed.** This note lists exactly what was touched and what a reviewer should
check.

## Files added

| File | Purpose |
|---|---|
| `frontend/lib/palette.ts` | Palette manifest and store. Names the five palettes, persists the choice, writes `data-palette` to `<html>`. |
| `frontend/lib/useTenantBrandOverride.ts` | Reads a tenant's brand colours from its ID token and overrides `--primary` / `--accent` at runtime. |
| `frontend/components/PaletteSwitcher.tsx` | Five preview cards. Rendered in governance only. |
| `frontend/lib/palette.test.ts` | 31 tests: store behaviour, stylesheet agreement, colour-injection rejection, contrast. |
| `frontend/check_palette_layer.py` | Offline audit of the stylesheet: custom-property cycles, dangling `var()` references, and WCAG contrast for every palette × mode pair. |

## Files changed

| File | Change | Size |
|---|---|---|
| `frontend/app/globals.css` | Token layer **appended**. | +552 / −0 |
| `frontend/app/layout.tsx` | `data-palette="graphite"` on `<html>` (now `cobalt`). | +5 / −1 |
| `frontend/components/ThemeInit.tsx` | Calls `hydratePalette()` on mount. Existing light/dark logic untouched. | +7 / −1 |
| `frontend/app/governance/client.tsx` | One import and one `<PaletteSwitcher />` mount. | +3 / −0 |

`globals.css` has **zero deleted lines**. Every rule above the appended block is
byte-identical, and the appended block only applies under `[data-palette]`, so
the stylesheet behaves exactly as before if the attribute is absent.

## How zero components needed editing

Every existing rule already reads from a fixed set of token names — `--bg`,
`--ink`, `--line`, `--primary`, `--cyan`, `--emerald`, `--warn`, `--navy`,
`--side-bg`, `--elev-1..3` and so on. The layer defines the new palette tokens
(`--bg-base`, `--text-primary`, `--accent`, …) and then a single **bridge** block
re-points the old names at the new ones:

```css
[data-palette] {
  --ink: var(--text-primary);
  --line: var(--border);
  --cyan: var(--accent-ui);
  /* … */
}
```

Changing `data-palette` re-resolves every custom property in the document, so
the sidebar, data grids, badges, command palette, copilot, negosim, spend cube
and governance screens all re-theme from one attribute write — no re-render, no
reload, no component touched.

### The bridge deliberately omits `--primary` and `--danger`

Those two names are declared directly by each palette block, so bridging them
would mean writing `--primary: var(--primary)` — a self-referential declaration.
CSS invalidates a custom-property cycle at computed-value time, so the property
becomes unset and silently inherits the `:root` default: the app would have
looked half-themed while the stylesheet read as correctly wired.
`lib/palette.test.ts` asserts no token is ever declared as its own value, and
`check_palette_layer.py` reports cycles.

## Three premises in the brief that did not hold

The brief specified a Tailwind theme extension, a Zustand store, and a Recharts
chart palette. **This project has none of the three** — `tailwindcss`,
`zustand` and `recharts` have zero entries in `frontend/package-lock.json`, and
the brief also forbids adding npm dependencies. There is likewise no tenant
branding API and no PDF generation anywhere in the repository.

| Asked for | Delivered instead |
|---|---|
| Tailwind theme extension mapping CSS vars to utilities | The bridge block above. It achieves the stated goal — existing class-like selectors keep working with no component edits — using the CSS the project actually has. No `tailwind.config` was added, because a config for an uninstalled framework is dead code that would read as if theming were wired up. |
| Zustand store | `lib/palette.ts` on `useSyncExternalStore`. Same contract (one value, `subscribe`, `getSnapshot`, persistence), zero dependencies, and the state is the DOM attribute rather than React state, so a switch re-renders nothing. |
| Chart palette "used by Recharts" | `--chart-1..8` tokens plus `.series-1..8` and `.chart-grid` helpers, since charts here are hand-drawn. Available to any future charting library unchanged. |
| "existing white-label brand colours, already used in tenant branding and PDF generation" | Read from **ID token claims** (`brand_primary`, `brand_accent`, and aliases, optionally nested under `branding` / `tenant_branding` / `tenant` / `white_label`). Keycloak issues them per tenant and the existing `tenant_id` isolation already covers them, so no endpoint, migration or backend change was needed. |

## Accessibility

`check_palette_layer.py` measures every text-on-surface pair that the UI actually
renders, in all ten palette/mode combinations, against WCAG AA. It found and
drove fixes for three real failures in the supplied palette values:

- **Sapphire light `--text-muted`** `#64748b` on `#f4f7fc` = 4.43:1 → `#5b6b82` (5.05:1).
- **Sapphire light accent** `#0ea5e9` on white = 2.77:1.
- **Amber light accent** `#f59e0b` on white = 2.15:1.

The two accent failures are resolved by a new `--accent-ui` token rather than by
darkening the brand hue. `--accent` keeps painting large gradient fills (a 64px
mark, the auth CTA), where the 3:1 non-text threshold does not apply, and
`--accent-ui` carries the AA-checked colour for small marks — the sidebar's
active-route bar and any accent text. It defaults to `--accent`, so only the two
palettes whose accent is genuinely too light on white override it, each reusing
its own documented hover step (`#0284c7`, `#d97706`). No new brand hue was
invented.

Procurement status colours are the opposite case: `--status-draft`,
`--status-in-review`, `--status-pending`, `--status-approved`,
`--status-rejected`, `--status-sealed`, `--status-expired`, `--status-at-risk`
and `--status-non-compliant` are declared **once** at `:root` and never per
palette, because they carry meaning rather than brand. A rejected badge is the
same red in every tenant's UI. Each mode has its own tuned set so the meanings
stay legible on both light and dark surfaces.

## Tenant isolation

The palette is a per-browser preference in `localStorage` and contains no tenant
data. The brand override is applied to the current document only, is never
persisted, and is torn down on unmount — so one tenant's brand cannot survive
into another tenant's session on a shared machine. Brand values are validated
hex-only: they are substituted into real CSS declarations, so `url(...)`,
`var(--x)`, a named colour or an embedded `;` is rejected and the palette
default stands.

## Verification

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npm run lint` | 0 errors, 5 warnings — all 5 pre-existing (4 × `<img>`, 1 × unused `initSpy` in `authboot.test.tsx`); the theming layer adds none |
| `npx vitest run` | 77 passed / 5 files (31 new) |
| `npm run build` | compiled, 18 routes prerendered |
| `python check_palette_layer.py` | 10 blocks, no cycles, no dangling refs, all contrast pairs pass |

## One behavioural change worth knowing

Graphite was the default at the time this migration landed, and its `--primary`
was `#1F2937` — near-black — where the previous token was `#1b6cff` blue. The
default appearance shifted from blue-accented to graphite, as specified.

**That default has since been replaced.** The brand is now Hyper Cobalt
`#0038FF` + Skin Sand `#FFD8B8` (`docs/05-frontend/design-system.md`), and the
default palette is `cobalt` — this document's Graphite rows describe what
shipped then, not what ships now. Links, primary buttons, panel summaries and
focus rings all follow `--primary`, which is cobalt. The sand accent drives the
logo-mark gradient, the card accent bar and the sidebar's active route, which is
Skin Sand with cobalt text on the cobalt sidebar — in every palette, because the
sidebar is the brand anchor and does not retheme.

## Not done, deliberately

No chart component was restyled and no existing chart was migrated to
`.series-N`; the helpers are available but adopting them per chart would mean
editing those charts, which the brief ruled out. Same for the `data-status`
attributes: the tokens and the attribute selectors are defined, but existing
status badges keep their `.badge.ok/.warn/.bad` classes until each caller is
changed.
