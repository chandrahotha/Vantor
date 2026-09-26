import { ImageResponse } from "next/og";

export const alt = "VANTOR — the intelligent procurement operating system";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** Social card, generated at build time.
 *  A static SVG in `public/` is not a reliable OG image: Slack, LinkedIn, X and
 *  WhatsApp all want raster (PNG/JPEG). This renders a real 1200×630 PNG from
 *  the same design tokens as `globals.css`, so the card can never drift from
 *  the product's palette. */
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#0A1931",
          padding: "72px 80px",
          fontFamily: "sans-serif",
        }}
      >
        {/* Accent rail — the same navy/blue/cyan/emerald ramp as the brand mark. */}
        <div style={{ display: "flex", gap: 12 }}>
          {["#1B6CFF", "#22D3EE", "#10B981"].map((c) => (
            <div key={c} style={{ width: 88, height: 8, borderRadius: 4, background: c }} />
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              fontSize: 96,
              fontWeight: 800,
              color: "#FFFFFF",
              letterSpacing: -3,
              lineHeight: 1,
            }}
          >
            VANTOR
          </div>
          <div style={{ fontSize: 40, color: "#22D3EE", marginTop: 24, fontWeight: 600 }}>
            Value. Intelligence. Control.
          </div>
          <div
            style={{
              fontSize: 30,
              color: "#94A3B8",
              marginTop: 28,
              maxWidth: 940,
              lineHeight: 1.35,
            }}
          >
            The procurement operating system that consolidates 10 products into one graph:
            suppliers, sourcing, contracts, purchase, spend and an evidence-cited AI copilot.
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div
            style={{
              fontSize: 26,
              color: "#FFFFFF",
              border: "2px solid #1B6CFF",
              borderRadius: 999,
              padding: "12px 28px",
            }}
          >
            AGPL-3.0-or-later
          </div>
          <div style={{ fontSize: 26, color: "#64748B" }}>Self-host free · FastAPI + Next.js</div>
          <div style={{ marginLeft: "auto", fontSize: 26, color: "#64748B" }}>Digi Tracks</div>
        </div>
      </div>
    ),
    { ...size },
  );
}
