import { readFile } from "node:fs/promises";
import path from "node:path";

import { ImageResponse } from "next/og";

export const alt = "VANTOR — the intelligent procurement operating system";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const ACCENT_RAILS = ["#1B6CFF", "#22D3EE", "#10B981"];

/** Social card, built from the REAL source art (vantor-icon-source.png — the
 *  glossy V+orbit squircle), not from a hand-drawn redraw. This is what keeps
 *  Slack/LinkedIn/X previews on brand instead of off-brand. */
export default async function OpengraphImage() {
  const brandPath = path.join(process.cwd(), "public", "icons", "icon-512.png");
  const brand = await readFile(brandPath);
  const brandSrc = `data:image/png;base64,${brand.toString("base64")}`;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background:
            "radial-gradient(1200px 620px at 18% 110%, rgba(34,211,238,0.16), transparent 55%), #0A1931",
          padding: "72px 80px",
          fontFamily: "sans-serif",
          position: "relative",
        }}
      >
        <div style={{ display: "flex", gap: 12 }}>
          {ACCENT_RAILS.map((c) => (
            <div key={c} style={{ width: 88, height: 8, borderRadius: 4, background: c }} />
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 48 }}>
          {/* The canonical mark, exact art, no redraw. */}
          <img src={brandSrc} style={{ width: 300, height: 300, borderRadius: 64, boxShadow: "0 24px 64px rgba(0,0,0,0.45)" }} alt="VANTOR" />
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: 92, fontWeight: 800, color: "#FFFFFF", letterSpacing: -3, lineHeight: 1 }}>
              VANTOR
            </div>
            <div style={{ fontSize: 36, color: "#22D3EE", marginTop: 18, fontWeight: 600 }}>
              Value. Intelligence. Control.
            </div>
            <div style={{ fontSize: 26, color: "#94A3B8", marginTop: 22, maxWidth: 740, lineHeight: 1.4 }}>
              One open procurement OS: suppliers, sourcing, contracts, purchase, spend and an
              evidence-cited AI copilot — self-host free.
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ fontSize: 24, color: "#FFFFFF", border: "2px solid #1B6CFF", borderRadius: 999, padding: "11px 26px" }}>
            AGPL-3.0-or-later
          </div>
          <div style={{ fontSize: 24, color: "#64748B" }}>FastAPI + Next.js + Postgres</div>
          <div style={{ marginLeft: "auto", fontSize: 24, color: "#64748B" }}>Digi Tracks</div>
        </div>
      </div>
    ),
    { ...size },
  );
}
