import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

/** Apple touch icon. iOS does not apply transparency or round masks to a
 *  favicon, so this is a separate opaque 180×180 render rather than a reuse. */
export default function AppleIcon() {
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
          fontSize: 120,
          fontWeight: 800,
        }}
      >
        V
      </div>
    ),
    { ...size },
  );
}
