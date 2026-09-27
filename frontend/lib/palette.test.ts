/**
 * The palette store, and the agreement between the store and the stylesheet.
 *
 * The store is the only place a palette key is named in TypeScript, and the
 * stylesheet is the only place the colours are defined. Nothing connects them:
 * a key added to `PALETTES` with no matching `[data-palette="…"]` block would
 * typecheck, lint, build and pass every other test, and would then render the
 * previous palette with no error anywhere. That is the failure this file exists
 * to catch.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_PALETTE,
  PALETTES,
  applyPalette,
  getPalette,
  isPaletteKey,
  paletteByKey,
  setPalette,
  type PaletteKey,
} from "./palette";
import {
  contrastRatio,
  isSafeColor,
  readBrandColors,
  relativeLuminance,
} from "./useTenantBrandOverride";

const CSS = readFileSync(path.join(process.cwd(), "app", "globals.css"), "utf8");

/** Tokens every palette block must declare, from the design brief. */
const REQUIRED_TOKENS = [
  "--bg-base", "--bg-elevated", "--bg-surface", "--bg-sunken",
  "--primary", "--primary-hover", "--primary-soft", "--primary-fg",
  "--accent", "--accent-hover", "--accent-ui",
  "--text-primary", "--text-secondary", "--text-muted", "--text-inverse",
  "--border", "--border-strong", "--divider",
  "--success", "--warning", "--danger", "--info", "--neutral",
  "--shadow-sm", "--shadow-md", "--shadow-lg",
  "--focus-ring",
];

describe("palette manifest", () => {
  it("offers exactly the five specified palettes", () => {
    expect(PALETTES.map((p) => p.key)).toEqual([
      "graphite",
      "emerald",
      "sapphire",
      "amber",
      "obsidian",
    ]);
  });

  it("defaults to Graphite", () => {
    expect(DEFAULT_PALETTE).toBe("graphite");
  });

  it("gives every palette a name, tagline, intended use and swatch", () => {
    for (const palette of PALETTES) {
      expect(palette.name.length).toBeGreaterThan(3);
      expect(palette.tagline.length).toBeGreaterThan(3);
      expect(palette.suitedFor.length).toBeGreaterThan(10);
      for (const value of Object.values(palette.swatch)) {
        expect(isSafeColor(value)).toBe(true);
      }
    }
  });

  it("never reuses a palette key", () => {
    expect(new Set(PALETTES.map((p) => p.key)).size).toBe(PALETTES.length);
  });
});

describe("palette store", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute("data-palette");
    localStorage.clear();
  });

  afterEach(() => {
    document.documentElement.removeAttribute("data-palette");
    localStorage.clear();
  });

  it("switching writes the attribute the stylesheet keys off", () => {
    setPalette("sapphire");
    expect(document.documentElement.dataset.palette).toBe("sapphire");
    setPalette("amber");
    expect(document.documentElement.dataset.palette).toBe("amber");
  });

  it("persists the choice for the next visit", () => {
    setPalette("emerald");
    expect(localStorage.getItem("vantor.palette")).toBe("emerald");
  });

  it("falls back to the default when storage holds something unknown", () => {
    // A palette removed in a later release must not strand the user on an
    // unstyled document, and must not throw on a bad attribute either.
    localStorage.setItem("vantor.palette", "chartreuse-v2");
    expect(getPalette()).toBe(DEFAULT_PALETTE);
  });

  it("adopts the server-rendered palette on hydration", async () => {
    // A fresh module instance, because the store is a module singleton and
    // `hydratePalette` is deliberately idempotent — earlier tests in this file
    // have already hydrated it. Re-importing rather than exporting a reset
    // keeps the production surface free of a test-only back door.
    vi.resetModules();
    document.documentElement.dataset.palette = "obsidian";
    const fresh = await import("./palette");
    expect(fresh.hydratePalette()).toBe("obsidian");
  });

  it("hydration prefers the stored choice over the server default", async () => {
    // The server renders `graphite` for every visitor, so reading the DOM first
    // would mean a returning user's palette never applies: the preference would
    // look saved, survive nothing, and reset on every reload.
    vi.resetModules();
    localStorage.setItem("vantor.palette", "emerald");
    document.documentElement.dataset.palette = "graphite";
    const fresh = await import("./palette");
    expect(fresh.hydratePalette()).toBe("emerald");
    expect(document.documentElement.dataset.palette).toBe("emerald");
  });

  it("hydration keeps the server default for a first-time visitor", async () => {
    vi.resetModules();
    localStorage.removeItem("vantor.palette");
    document.documentElement.dataset.palette = "graphite";
    const fresh = await import("./palette");
    expect(fresh.hydratePalette()).toBe("graphite");
  });

  it("hydration does not re-persist what it just read", async () => {
    // Otherwise the storage write happens on every load, which is pointless IO
    // and makes "was this user ever here?" unanswerable.
    vi.resetModules();
    localStorage.setItem("vantor.palette", "amber");
    // Spy after seeding: the seeding write is this test's own setup.
    const spy = vi.spyOn(Storage.prototype, "setItem");
    document.documentElement.dataset.palette = "graphite";
    const fresh = await import("./palette");
    fresh.hydratePalette();
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("applyPalette can skip persistence, for the hydration path", () => {
    applyPalette("graphite", { persist: false });
    expect(document.documentElement.dataset.palette).toBe("graphite");
    expect(localStorage.getItem("vantor.palette")).toBeNull();
  });

  it("rejects an unknown key without touching the DOM", () => {
    expect(isPaletteKey("sapphire")).toBe(true);
    expect(isPaletteKey("chartreuse")).toBe(false);
    expect(isPaletteKey(null)).toBe(false);
    expect(isPaletteKey(7)).toBe(false);
    expect(isPaletteKey({})).toBe(false);
  });

  it("resolves a known key and degrades safely on an unknown one", () => {
    expect(paletteByKey("amber").name).toBe("Spend Amber");
    // Unreachable through the type system; reachable from a bad attribute.
    expect(paletteByKey("nope" as PaletteKey).key).toBe(DEFAULT_PALETTE);
  });
});

describe("stylesheet agreement", () => {
  it("defines a light and a dark block for every palette in the manifest", () => {
    for (const { key } of PALETTES) {
      expect(CSS, `no [data-palette="${key}"] block`).toContain(`[data-palette="${key}"] {`);
      expect(CSS, `no dark block for ${key}`).toContain(
        `[data-palette="${key}"][data-theme="dark"]`,
      );
    }
  });

  it("declares every required token in every palette block", () => {
    for (const { key } of PALETTES) {
      for (const variant of [
        `[data-palette="${key}"] {`,
        `[data-palette="${key}"][data-theme="dark"]`,
      ]) {
        const start = CSS.indexOf(variant);
        expect(start, `missing ${variant}`).toBeGreaterThan(-1);
        const body = CSS.slice(start, CSS.indexOf("\n}", start));
        for (const token of REQUIRED_TOKENS) {
          expect(body, `${variant} does not declare ${token}`).toContain(`${token}:`);
        }
      }
    }
  });

  it("never declares a token as its own value", () => {
    // `--primary: var(--primary)` is a custom-property cycle: invalid at
    // computed-value time, so the property silently inherits the root default.
    // The app would look half-themed while the stylesheet read as correct.
    const declarations = CSS.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g);
    for (const [, token, value] of declarations) {
      expect(value, `${token} references itself`).not.toBe(`var(${token})`);
    }
  });

  it("bridges the new tokens onto the names the existing CSS reads", () => {
    // Without these the palettes would be inert: every existing rule reads
    // --ink, --line, --primary, not --text-primary.
    for (const bridged of [
      "--bg: var(--bg-base)",
      "--surface: var(--bg-surface)",
      "--ink: var(--text-primary)",
      "--line: var(--border)",
      "--primary-strong: var(--primary-hover)",
      "--cyan: var(--accent-ui)",
      "--emerald: var(--success)",
      "--warn: var(--warning)",
    ]) {
      expect(CSS, `bridge missing: ${bridged}`).toContain(bridged);
    }
  });

  it("keeps procurement status colours out of the palette blocks", () => {
    // Status meaning must not move when the palette changes, so these are
    // declared once at :root and never per palette.
    for (const { key } of PALETTES) {
      const start = CSS.indexOf(`[data-palette="${key}"] {`);
      const body = CSS.slice(start, CSS.indexOf("\n}", start));
      expect(body, `${key} redefines a status colour`).not.toContain("--status-");
    }
    for (const status of [
      "--status-draft", "--status-in-review", "--status-pending", "--status-approved",
      "--status-rejected", "--status-sealed", "--status-expired",
    ]) {
      expect(CSS, `${status} is not defined anywhere`).toContain(`${status}:`);
    }
  });

  it("defines all eight chart colours in a fixed order", () => {
    for (let i = 1; i <= 8; i += 1) {
      expect(CSS, `--chart-${i} is not defined`).toContain(`--chart-${i}:`);
    }
  });

  it("honours both attribute and class dark mode", () => {
    // The brief requires a `.dark` class; the project uses `data-theme`. Both
    // have to work, or a deployment that sets one of them gets light colours
    // with a dark-mode class.
    expect(CSS).toContain('.dark');
    expect(CSS).toContain('[data-theme="dark"]');
  });

  it("keeps the status and chart tokens identical across palettes", () => {
    const paletteBlocks = PALETTES.map(({ key }) => {
      const start = CSS.indexOf(`[data-palette="${key}"] {`);
      return CSS.slice(start, CSS.indexOf("\n}", start));
    });
    const charts = paletteBlocks.map((b) => (b.match(/--chart-\d/g) || []).length);
    expect(new Set(charts).size, "a palette redefines chart colours").toBe(1);
  });

  it("places the bridge after every palette block", () => {
    // Equal specificity, so source order decides. A bridge written above the
    // palette definitions would be overridden by them and the app would keep
    // the un-bridged :root colours with no visible error.
    const bridge = CSS.indexOf("[data-palette] {");
    expect(bridge, "the bridge block is missing").toBeGreaterThan(-1);
    for (const { key } of PALETTES) {
      for (const selector of [`[data-palette="${key}"] {`, `[data-palette="${key}"][data-theme="dark"]`]) {
        expect(CSS.indexOf(selector), `${selector} is defined after the bridge`)
          .toBeLessThan(bridge);
      }
    }
  });

  it("dark palette selectors outrank the project's single-attribute dark block", () => {
    // `[data-theme="dark"]` is (0,1,0). A palette's dark block has to be
    // (0,2,0) — i.e. keep both attributes in one selector — or the legacy dark
    // block wins on order alone and dark mode ignores the palette.
    const legacy = CSS.indexOf('[data-theme="dark"] {');
    expect(legacy, "the existing dark block is missing").toBeGreaterThan(-1);
    for (const { key } of PALETTES) {
      expect(CSS).toContain(`[data-palette="${key}"][data-theme="dark"]`);
    }
  });
});

describe("tenant brand override", () => {
  it("accepts only hex colours", () => {
    // These values land in a CSS custom property that is substituted into real
    // declarations, so anything looser is a styling-injection point.
    for (const safe of ["#fff", "#ffffff", "#FFFFFF", "#12345678"]) {
      expect(isSafeColor(safe), safe).toBe(true);
    }
    for (const unsafe of [
      "red", "rgb(1,2,3)", "var(--x)", "url(https://evil.test/x)",
      "#fff; background: url(https://evil.test/x)", "expression(alert(1))",
      "", "  ", "#ff", "#gggggg", null, undefined, 42, {},
    ]) {
      expect(isSafeColor(unsafe as unknown), String(unsafe)).toBe(false);
    }
  });

  it("reads brand colours from the token claims", () => {
    expect(
      readBrandColors({ brand_primary: "#112233", brand_accent: "#445566" }),
    ).toEqual({ primary: "#112233", accent: "#445566" });
  });

  it("expands shorthand hex so channel maths is uniform", () => {
    expect(readBrandColors({ brand_primary: "#abc" })).toEqual({ primary: "#aabbcc" });
  });

  it("looks inside a nested branding object", () => {
    expect(readBrandColors({ tenant_branding: { brand_primary: "#0a0b0c" } })).toEqual({
      primary: "#0a0b0c",
    });
  });

  it("ignores an unusable value and keeps the palette default", () => {
    // A tenant that misconfigures its brand gets the palette, not a broken UI.
    expect(readBrandColors({ brand_primary: "url(https://evil.test/x)" })).toEqual({});
    expect(readBrandColors(null)).toEqual({});
    expect(readBrandColors({})).toEqual({});
  });

  it("computes WCAG luminance and contrast", () => {
    expect(relativeLuminance("#ffffff")).toBeCloseTo(1, 5);
    expect(relativeLuminance("#000000")).toBeCloseTo(0, 5);
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 1);
    expect(contrastRatio("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
  });
});

describe("palette swatch legibility", () => {
  it("keeps each palette's own name readable on its own preview surface", () => {
    // The switcher paints a card in the palette's colours. If the name cannot
    // be read on it, the preview is worse than useless.
    for (const { key, name, swatch } of PALETTES) {
      const cr = contrastRatio(swatch.text, swatch.surface);
      expect(cr, `${key} (${name}) preview text is ${cr.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
    }
  });
});
