import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

/** Favicon, generated from the brand mark's hexagon + V so it stays in sync
 *  with `assets/brand/favicon.svg` without a manual resize step. */
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0A1931",
          color: "#22D3EE",
          fontSize: 22,
          fontWeight: 800,
          borderRadius: 6,
        }}
      >
        V
      </div>
    ),
    { ...size },
  );
}
