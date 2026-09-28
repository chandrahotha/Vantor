/**
 * Palette store — the single source of truth for the active design palette.
 *
 * Why this is not Zustand
 * -----------------------
 * The brief asked for a Zustand store. This project has no Zustand dependency
 * (and the brief also forbids adding npm dependencies), so the store is built on
 * React's own `useSyncExternalStore`: a module-level snapshot plus a subscriber
 * set. That gives the same contract a Zustand store would — one state value,
 * `subscribe`, `getSnapshot`, and persistence — with zero bytes added to the
 * bundle and no dependency to keep in step with React 19.
 *
 * The state is the `data-palette` attribute on `<html>`, not React state. CSS
 * custom properties resolve the whole application from that one attribute, so a
 * palette change is a single DOM write: no re-render of any component, no
 * context provider above the tree, and nothing for a page to get out of sync.
 * React re-renders only the components that call `usePalette()` — currently the
 * switcher itself, which is all that needs to.
 *
 * Tenant isolation: the palette is a per-browser preference, like the existing
 * `vantor.theme`. It is keyed by nothing but the local browser, and it contains
 * no tenant data, so it cannot leak one tenant's choice to another. The tenant
 * *brand* colours are a separate concern — see `useTenantBrandOverride`.
 */

import { useSyncExternalStore } from "react";

export type PaletteKey =
  | "cobalt"
  | "emerald"
  | "sapphire"
  | "amber"
  | "obsidian";

export type PaletteDef = {
  key: PaletteKey;
  name: string;
  /** Two or three words, for the switcher's preview card. */
  tagline: string;
  /** Which part of the procurement graph this palette is tuned for. */
  suitedFor: string;
  /** Preview swatches, in the order they are painted on the card. */
  swatch: { primary: string; accent: string; surface: string; text: string };
};

export const DEFAULT_PALETTE: PaletteKey = "cobalt";

export const PALETTES: readonly PaletteDef[] = [
  {
    key: "cobalt",
    name: "Vantor Cobalt",
    tagline: "Hyper Cobalt + Skin Sand",
    suitedFor: "Default. Whole-platform navigation, cross-product oversight.",
    swatch: { primary: "#0038ff", accent: "#ffd8b8", surface: "#ffffff", text: "#172033" },
  },
  {
    key: "emerald",
    name: "Sourcing Emerald",
    tagline: "Supplier qualification and RFQ",
    suitedFor: "Sourcing, RFQ comparison, supplier onboarding and qualification.",
    swatch: { primary: "#065f46", accent: "#0d9488", surface: "#ffffff", text: "#0b1f1a" },
  },
  {
    key: "sapphire",
    name: "Contract Sapphire",
    tagline: "Obligations, compliance, renewals",
    suitedFor: "Contract lifecycle, compliance, obligations and renewal tracking.",
    swatch: { primary: "#1d4ed8", accent: "#0ea5e9", surface: "#ffffff", text: "#0b1b33" },
  },
  {
    key: "amber",
    name: "Spend Amber",
    tagline: "Leakage, should-cost, price intel",
    suitedFor: "Spend cube, leakage, maverick detection, should-cost, price cases.",
    swatch: { primary: "#92400e", accent: "#f59e0b", surface: "#ffffff", text: "#1f1300" },
  },
  {
    key: "obsidian",
    name: "Negotiation Obsidian",
    tagline: "High-contrast command center",
    suitedFor: "Negotiation simulator, copilot command center, dark-room NOC use.",
    swatch: { primary: "#0f172a", accent: "#6c47ff", surface: "#ffffff", text: "#0a0a0a" },
  },
] as const;

const STORAGE_KEY = "vantor.palette";

const PALETTE_KEYS = new Set<string>(PALETTES.map((p) => p.key));

export function isPaletteKey(value: unknown): value is PaletteKey {
  return typeof value === "string" && PALETTE_KEYS.has(value);
}

export function paletteByKey(key: PaletteKey): PaletteDef {
  const found = PALETTES.find((p) => p.key === key);
  // `key` is typed, so this is unreachable through the type system. It is kept
  // because the value can still arrive from localStorage or a URL at runtime,
  // and a throw here would blank the app rather than fall back to the default.
  return found ?? PALETTES[0];
}

/* --- the store ------------------------------------------------------------ */

let current: PaletteKey = DEFAULT_PALETTE;
let hydrated = false;
const listeners = new Set<() => void>();

function readDom(): PaletteKey | null {
  if (typeof document === "undefined") return null;
  const attr = document.documentElement.dataset.palette;
  return isPaletteKey(attr) ? attr : null;
}

function readStorage(): PaletteKey | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return isPaletteKey(raw) ? raw : null;
  } catch {
    // Private mode, disabled storage, or a sandboxed iframe. A missing
    // preference is not an error; the default simply applies.
    return null;
  }
}

/**
 * Adopt the persisted palette into module state.
 *
 * Precedence is **stored choice, then the DOM, then the default**. The DOM
 * attribute is server-rendered as `cobalt` for everyone, so reading it first
 * would mean the stored choice never applies: the preference would appear to be
 * saved, survive nothing, and reset to Cobalt on every reload. The
 * server-rendered value is therefore only a fallback — the pre-JS default that
 * stops a flash, and the value to keep for a first-time visitor.
 *
 * Called by `ThemeInit` on mount, before anything reads `usePalette()`, so the
 * first subscriber sees the real value rather than the default and the switcher
 * cannot render "Cobalt selected" for a user who chose Emerald.
 */
export function hydratePalette(): PaletteKey {
  if (hydrated) return current;
  hydrated = true;
  current = readStorage() ?? readDom() ?? DEFAULT_PALETTE;
  // Re-assert even when the DOM already matches, so the first subscriber and
  // the DOM can never disagree about what is active.
  applyPalette(current, { persist: false });
  return current;
}

/** The active palette. Safe on the server: returns the default there. */
export function getPalette(): PaletteKey {
  if (!hydrated && typeof window !== "undefined") return hydratePalette();
  return current;
}

function emit(): void {
  for (const listener of listeners) listener();
}

export function subscribePalette(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Write the palette to `<html>` and persist it.
 *
 * The attribute write is the entire switch: every `[data-palette]` rule in
 * `globals.css` re-resolves, so the change is instant and needs no reload.
 */
export function applyPalette(
  key: PaletteKey,
  options: { persist?: boolean } = {},
): PaletteKey {
  const { persist = true } = options;
  current = key;
  if (typeof document !== "undefined") {
    document.documentElement.dataset.palette = key;
  }
  if (persist && typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, key);
    } catch {
      // A palette that cannot be remembered still applies for this session,
      // which is a better outcome than refusing to switch.
    }
  }
  emit();
  return key;
}

export function setPalette(key: PaletteKey): PaletteKey {
  return applyPalette(key);
}

export function resetPalette(): PaletteKey {
  return applyPalette(DEFAULT_PALETTE);
}

/**
 * Subscribe a component to the active palette.
 *
 * `getSnapshot` must return a cached value, not a fresh object, or React will
 * loop. `current` is a primitive held in module scope, so it is stable between
 * calls and this is safe.
 */
export function usePalette(): PaletteKey {
  return useSyncExternalStore(subscribePalette, getPalette, () => DEFAULT_PALETTE);
}

/**
 * Read the active mode (light or dark) from the existing theme mechanism.
 *
 * Deliberately not duplicated here. `data-theme` is owned by `ThemeInit` and
 * `toggleTheme`; a second copy of that state would be a second thing to keep
 * correct, and the switcher only needs to label which mode its preview shows.
 */
export function currentMode(): "light" | "dark" {
  if (typeof document === "undefined") return "light";
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}
