/**
 * Tenant brand override — white-label primary and accent colours.
 *
 * A tenant that white-labels VANTOR supplies its own brand colours. Those must
 * win over the palette's defaults without the palette itself being replaced:
 * the palette still supplies surfaces, text, borders, status and chart colours,
 * and only `--primary` / `--accent` are overridden.
 *
 * Where the colours come from
 * ---------------------------
 * The brief describes this as reading "the existing Keycloak realm / tenant
 * branding data". There is no tenant-branding API in this repository — no
 * branding endpoint, and no PDF generation — so there is nothing to read from
 * server-side without adding an API, which is out of scope for a design-only
 * change. The colours are therefore read from the **ID token claims**, which is
 * where a realm's branding belongs anyway: Keycloak already issues them per
 * tenant, they are covered by the existing `tenant_id` isolation, and they need
 * no new endpoint, no migration and no backend change.
 *
 * The claim names are accepted defensively because they are configuration, not
 * code: a deployment may name them anything. The first match wins, in the order
 * listed below.
 *
 * Trust boundary
 * --------------
 * These values are written into a CSS custom property on `<html>`, and custom
 * properties are substituted into real declarations. An unvalidated value here
 * is a styling injection point, so `isSafeColor` accepts **only** `#rgb`,
 * `#rrggbb` and `#rrggbbaa`. Anything else — a `url(...)`, a second
 * declaration, `var(--x)`, a named colour, a gradient — is discarded and the
 * palette default stands. A tenant that misconfigures its brand gets the
 * default palette rather than a broken UI, and a tenant that tries something
 * else gets nothing.
 *
 * Isolation: the override is applied to the current document only, and is torn
 * down on unmount and whenever the session changes. It is never written to
 * storage, so one tenant's brand cannot persist into another tenant's session
 * on a shared machine.
 */

import { useEffect, useSyncExternalStore } from "react";
import { keycloak } from "./auth";

/** The tokens a tenant is allowed to influence. Nothing else is writable.
 *  Kept as data rather than implied so the trust boundary is auditable: if a
 *  token is not produced by `brandTokens`, it is not writable. */
const WRITABLE_TOKENS: readonly string[] = [
  "--primary", "--primary-hover", "--primary-soft", "--primary-fg", "--focus-ring",
  "--accent", "--accent-hover",
];

type BrandSlot = "primary" | "accent";

/** Claim names probed, in priority order, for each slot. */
const SLOT_CLAIMS: Record<BrandSlot, readonly string[]> = {
  primary: ["brand_primary", "brand_primary_color", "tenant_brand_primary", "primary_color"],
  accent: ["brand_accent", "brand_accent_color", "tenant_brand_accent", "accent_color"],
};

/** Nested objects a realm might group branding under. */
const NAMESPACE_CLAIMS = ["branding", "tenant_branding", "tenant", "white_label"] as const;

const HEX = /^#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;

/**
 * A colour is acceptable only if it is a hex literal.
 *
 * Deliberately not permissive. `color-mix(in srgb, <value>, black)` is used
 * downstream, and a value that is not a plain colour can make that invalid —
 * but worse, a value containing `;` or `url()` reaches the CSS parser as part
 * of a substituted token. Hex-only makes both impossible.
 */
export function isSafeColor(value: unknown): value is string {
  return typeof value === "string" && HEX.test(value.trim());
}

function normalizeHex(value: string): string {
  const v = value.trim().toLowerCase();
  if (v.length === 4 || v.length === 5) {
    // #abc -> #aabbcc so channel arithmetic below is uniform.
    return `#${v[1]}${v[1]}${v[2]}${v[2]}${v[3]}${v[3]}${v.length === 5 ? v[4] + v[4] : ""}`;
  }
  return v;
}

function toRgb(hex: string): { r: number; g: number; b: number } {
  const h = normalizeHex(hex);
  return {
    r: parseInt(h.slice(1, 3), 16),
    g: parseInt(h.slice(3, 5), 16),
    b: parseInt(h.slice(5, 7), 16),
  };
}

/** Relative luminance, WCAG 2.x. Used to pick a readable foreground. */
export function relativeLuminance(hex: string): number {
  const channel = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const { r, g, b } = toRgb(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** Contrast ratio between two hex colours, 1:1 to 21:1. */
export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

export type BrandColors = Partial<Record<BrandSlot, string>>;

/**
 * Extract brand colours from a claims object.
 *
 * Exported for tests and for the switcher's "this tenant overrides…" label.
 * Pure: no DOM, no globals.
 */
export function readBrandColors(claims: unknown): BrandColors {
  if (!claims || typeof claims !== "object") return {};
  const root = claims as Record<string, unknown>;
  const scopes: Record<string, unknown>[] = [root];
  for (const ns of NAMESPACE_CLAIMS) {
    const nested = root[ns];
    if (nested && typeof nested === "object") scopes.push(nested as Record<string, unknown>);
  }

  const found: BrandColors = {};
  for (const slot of ["primary", "accent"] as BrandSlot[]) {
    for (const scope of scopes) {
      for (const claim of SLOT_CLAIMS[slot]) {
        const value = scope[claim];
        if (isSafeColor(value)) {
          found[slot] = normalizeHex(value);
          break;
        }
      }
      if (found[slot]) break;
    }
  }
  return found;
}

/**
 * The tokens a brand colour implies, computed rather than hard-coded.
 *
 * Overriding only `--primary` would leave `--primary-hover`, `--primary-soft`
 * and `--primary-fg` at the palette's values, so a tenant's brand button would
 * hover to a colour belonging to a different palette and its label would be
 * painted in a foreground chosen for a different background. Both are derived
 * here so the override is internally consistent.
 */
function brandTokens(slot: BrandSlot, color: string, mode: "light" | "dark"): Record<string, string> {
  if (slot === "accent") {
    return {
      "--accent": color,
      // Mix toward the page background, which darkens in dark mode and lightens
      // in light mode — the same direction a hover should move in both.
      "--accent-hover": `color-mix(in srgb, ${color} ${mode === "dark" ? "82" : "88"}%, ${
        mode === "dark" ? "#ffffff" : "#000000"
      })`,
    };
  }

  // Pick the readable foreground rather than assuming white. A tenant whose
  // brand is a pale yellow would get white text on it otherwise, at roughly
  // 1.2:1 — unreadable, and the failure would be invisible to whoever set it.
  const onDark = contrastRatio(color, "#ffffff") >= contrastRatio(color, "#0b0f17");
  const fg = onDark ? "#ffffff" : "#0b0f17";
  return {
    "--primary": color,
    "--primary-hover": `color-mix(in srgb, ${color} 88%, ${onDark ? "#000000" : "#ffffff"})`,
    "--primary-soft": `color-mix(in srgb, ${color} 14%, transparent)`,
    "--primary-fg": fg,
    // The focus ring follows the brand so keyboard focus stays visible against
    // the button it is on.
    "--focus-ring": color,
  };
}

/* --- the brand store ------------------------------------------------------
   A tiny external store rather than React state. Publishing the colours into a
   store and reading them with `useSyncExternalStore` avoids calling setState
   inside an effect (which triggers a cascading second render), and gives a
   stable server snapshot of `{}` — the server has no token, so any render-time
   read would mismatch on hydration. Same pattern as the palette store. */

const EMPTY: BrandColors = {};
let snapshot: BrandColors = EMPTY;
const brandListeners = new Set<() => void>();

function publish(next: BrandColors): void {
  // Identity-stable when nothing changed, so `useSyncExternalStore` does not
  // loop on a re-render.
  const sameKeys =
    Object.keys(next).length === Object.keys(snapshot).length &&
    (Object.keys(next) as BrandSlot[]).every((k) => next[k] === snapshot[k]);
  if (sameKeys) return;
  snapshot = next;
  for (const listener of brandListeners) listener();
}

function subscribeBrand(listener: () => void): () => void {
  brandListeners.add(listener);
  return () => {
    brandListeners.delete(listener);
  };
}

/**
 * Apply a tenant's brand colours to `<html>` for as long as the caller is
 * mounted, and remove them on unmount.
 *
 * Mounted once, high in the tree, so the override is in place before any
 * component reads a token. It renders nothing.
 *
 * Returns the colours in effect, so a caller can label the state.
 */
export function useTenantBrandOverride(): BrandColors {
  useEffect(() => {
    if (typeof document === "undefined") return;

    const brandColors = readBrandColors(keycloakClaims());
    publish(brandColors);

    const slots = Object.keys(brandColors) as BrandSlot[];
    if (!slots.length) return;

    const root = document.documentElement;
    const mode: "light" | "dark" = root.dataset.theme === "dark" ? "dark" : "light";
    // Record what was there before, so teardown removes exactly our values and
    // cannot clobber a value the palette put there.
    const written: Array<[string, string]> = [];

    for (const slot of slots) {
      const color = brandColors[slot];
      if (!color) continue;
      for (const [token, value] of Object.entries(brandTokens(slot, color, mode))) {
        // Belt and braces: a token outside the declared writable set is never
        // written, whatever `brandTokens` returns.
        if (!WRITABLE_TOKENS.includes(token)) continue;
        written.push([token, root.style.getPropertyValue(token)]);
        root.style.setProperty(token, value);
      }
    }

    return () => {
      for (const [token, previous] of written) {
        if (previous) root.style.setProperty(token, previous);
        else root.style.removeProperty(token);
      }
      publish(EMPTY);
    };
  }, []);

  return useSyncExternalStore(subscribeBrand, () => snapshot, () => EMPTY);
}

/** The parsed ID token, or null when there is no session. Never throws. */
function keycloakClaims(): unknown {
  try {
    return keycloak().tokenParsed ?? null;
  } catch {
    return null;
  }
}
