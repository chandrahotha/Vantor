"use client";

/**
 * Palette switcher — five preview cards for the governance settings screen.
 *
 * Design constraints this component is built to:
 *
 * - **No colour as the only signal.** Each card names its palette in text and
 *   the selected one carries a check, `aria-pressed` and a heavier border, so
 *   selection is legible without colour vision and to a screen reader.
 * - **Evidence-cited, human-review language preserved.** The card footer states
 *   what each palette is tuned for, so choosing one is an informed choice about
 *   which part of the procurement graph someone works in, not decoration.
 * - **Instant.** Selecting writes `data-palette` on `<html>` and nothing else.
 *   No route change, no reload, no re-render of the pages around it.
 * - **Density.** A five-across grid of compact cards, matching the 8pt grid and
 *   the `--fs-*` scale already in the design system.
 *
 * It reads the active palette from the store and writes through
 * `setPalette`, so it stays correct if the palette is changed anywhere else.
 */

import { PALETTES, paletteByKey, setPalette, usePalette, type PaletteKey } from "../lib/palette";
import { useTenantBrandOverride } from "../lib/useTenantBrandOverride";

function PaletteCard({
  palette,
  selected,
  onSelect,
}: {
  palette: (typeof PALETTES)[number];
  selected: boolean;
  onSelect: (key: PaletteKey) => void;
}) {
  const s = palette.swatch;
  return (
    <button
      type="button"
      // A plain button with `aria-pressed`, not `role="radio"`.
      //
      // A `radiogroup` obliges the author to implement roving tabindex and arrow-key
      // navigation: a screen-reader user is told "radio group" and then finds that
      // only Tab and Enter work, which is worse than the semantics that were
      // there before. `role="radio"` on a `<button>` also overrides the native
      // button role, losing the activation behaviour along with it. Five
      // independent toggles, each reachable by Tab and operable with Enter or
      // Space, is what the interaction actually is.
      aria-pressed={selected}
      data-palette-card={palette.key}
      data-selected={selected ? "true" : "false"}
      onClick={() => onSelect(palette.key)}
      style={{
        all: "unset",
        cursor: "pointer",
        display: "block",
        borderRadius: "var(--radius-l)",
        border: `1px solid ${selected ? "var(--primary)" : "var(--line)"}`,
        boxShadow: selected ? "0 0 0 1px var(--primary), var(--shadow-sm)" : "var(--shadow-sm)",
        background: "var(--surface)",
        overflow: "hidden",
        transition: "border-color var(--t-fast) var(--ease), box-shadow var(--t-fast) var(--ease)",
      }}
    >
      {/* Preview: a miniature of the palette's own surfaces, not a screenshot. */}
      <div
        aria-hidden="true"
        style={{
          background: s.surface,
          borderBottom: "1px solid var(--line)",
          padding: "10px 12px 12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 9 }}>
          <span
            style={{
              width: 16,
              height: 16,
              borderRadius: 5,
              background: s.primary,
              flex: "0 0 auto",
            }}
          />
          <span
            style={{
              width: 44,
              height: 6,
              borderRadius: 3,
              background: s.text,
              opacity: 0.85,
            }}
          />
          <span style={{ flex: 1 }} />
          <span
            style={{
              width: 26,
              height: 12,
              borderRadius: 999,
              background: s.accent,
            }}
          />
        </div>
        {/* Three "rows", the middle one zebra — mirrors the data grid. */}
        {[0, 1, 2].map((row) => (
          <div
            key={row}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              background: row === 1 ? s.surface : "transparent",
              opacity: 1 - row * 0.22,
            }}
          >
            <span style={{ width: 38, height: 4, borderRadius: 2, background: s.text }} />
            <span style={{ flex: 1 }} />
            <span style={{ width: 22, height: 4, borderRadius: 2, background: s.accent }} />
          </div>
        ))}
      </div>

      <div style={{ padding: "10px 12px 12px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <strong style={{ fontSize: "var(--fs-13)", color: "var(--ink)" }}>{palette.name}</strong>
          {selected ? (
            <span style={{ fontSize: "var(--fs-11)", color: "var(--primary)", fontWeight: 700 }}>
              &#10003; active
            </span>
          ) : null}
        </div>
        <div style={{ fontSize: "var(--fs-11)", color: "var(--muted)", marginTop: 2 }}>
          {palette.tagline}
        </div>
        <div style={{ fontSize: "var(--fs-11)", color: "var(--faint)", marginTop: 5, lineHeight: 1.5 }}>
          {palette.suitedFor}
        </div>
      </div>
    </button>
  );
}

export default function PaletteSwitcher() {
  const active = usePalette();
  const brand = useTenantBrandOverride();

  return (
    <div className="panel" data-palette-switcher="true">
      <h2 style={{ margin: 0, fontSize: "var(--fs-16)" }}>Colour palette</h2>
      <p style={{ margin: "6px 0 14px", fontSize: "var(--fs-13)", color: "var(--muted)", maxWidth: "78ch" }}>
        Five enterprise palettes, each with a light and a dark variant. The palette changes surfaces,
        text and accent colour only. Procurement status colours — approved, rejected, pending, sealed,
        expired, at-risk, non-compliant — stay identical in every palette, because they carry meaning
        rather than brand.
      </p>

      <div
        role="group"
        aria-label="Colour palette"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))",
          gap: 12,
        }}
      >
        {PALETTES.map((palette) => (
          <PaletteCard
            key={palette.key}
            palette={palette}
            selected={palette.key === active}
            onSelect={setPalette}
          />
        ))}
      </div>

      <p style={{ margin: "14px 0 0", fontSize: "var(--fs-12)", color: "var(--muted)" }}>
        Active: <strong style={{ color: "var(--ink)" }}>{paletteByKey(active).name}</strong>. The
        choice is stored in this browser and applies immediately, with no reload.
        {brand.primary || brand.accent ? (
          <>
            {" "}
            This tenant overrides {brand.primary ? "primary" : ""}
            {brand.primary && brand.accent ? " and " : ""}
            {brand.accent ? "accent" : ""} with its own brand colour; everything else follows the
            palette.
          </>
        ) : null}
      </p>
    </div>
  );
}
