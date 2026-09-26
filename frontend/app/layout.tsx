import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"),
  title: "VANTOR — Procurement OS by Digi Tracks",
  description: "One-stop procurement: suppliers, sourcing, contracts, purchase, spend, approvals and AI copilot.",
  keywords: ["procurement", "sourcing", "RFQ", "purchase orders", "contracts", "spend analysis", "approvals", "supplier management", "Digi Tracks", "Vantor"],
  authors: [{ name: "Digi Tracks" }],
  robots: { index: true, follow: true },
  openGraph: {
    title: "VANTOR — Intelligent Procurement Operating System",
    description: "Value. Intelligence. Control. Free, self-hostable procurement OS by Digi Tracks.",
    type: "website",
    images: ["/logo.svg"],
  },
  twitter: { card: "summary", title: "VANTOR by Digi Tracks", description: "One-stop procurement OS." },
  icons: { icon: "/logo.svg" },
};

export default function Root({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

