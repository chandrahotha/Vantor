import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import ThemeInit from "../components/ThemeInit";
import AppProviders from "../components/AppProviders";
import NextTopLoader from "nextjs-toploader";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
  weight: ["400", "500", "600", "700", "800"],
});
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
  weight: ["400", "600", "700"],
});

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";
const TITLE = "VANTOR — Intelligent Procurement Operating System";

export const metadata: Metadata = {
  metadataBase: new URL(APP_URL),
  title: {
    default: TITLE,
    template: `%s · VANTOR`,
  },
  description:
    "VANTOR is an open-source procurement operating system that consolidates 10 products into one graph: supplier intelligence, RFQ and sourcing, contracts, purchase orders, spend analytics and an evidence-cited AI copilot. Self-host free.",
  applicationName: "VANTOR",
  authors: [{ name: "Digi Tracks", url: "https://github.com/chandrahotha" }],
  creator: "Digi Tracks",
  publisher: "Digi Tracks",
  category: "business",
  keywords: [
    "procurement software", "procurement operating system", "open source procurement",
    "supplier management", "supplier risk", "strategic sourcing", "RFQ", "RFP",
    "quotation comparison", "contract lifecycle management", "CLM", "purchase order",
    "purchase requisition", "three way match", "spend analytics", "spend intelligence",
    "should-cost model", "maverick spend", "savings tracking", "procurement approval workflow",
    "supplier onboarding", "supplier qualification", "negotiation simulator",
    "procurement AI copilot", "human in the loop AI", "Keycloak OIDC", "Row Level Security",
    "FastAPI", "Next.js", "Postgres", "Apache-2.0", "self-hosted", "open source ERP", "Digi Tracks",
  ],
  // Honest indexing posture: every route requires a signed-in session, so a crawler
  // can only ever see the identity-provider redirect. The discoverable surfaces
  // for this product are the docs site and the GitHub repository.
  robots: { index: false, follow: false, nocache: true, googleBot: { index: false, follow: false } },
  alternates: { canonical: "/" },
  manifest: "/manifest.webmanifest",
  // Two presentations of the one brand, both rasterized from assets/brand/ by
  // scripts/build_brand_icons.py:
  //   vantor-icon-source.png          V+orbit on its navy squircle — the app
  //                                  icons below, because an OS renders a
  //                                  favicon on an unknown background and it
  //                                  needs its own field.
  //   vantor-icon-bg-less-source.png  the same V+orbit alone — the in-app
  //                                  sidebar, whose surface is #0a1931, the same
  //                                  navy as the squircle. Drawing the squircle
  //                                  there produced a dark box with a muddy edge
  //                                  rather than a mark.
  // No generated letter-marks anywhere.
  icons: {
    icon: [
      { url: "/icons/favicon-16.png", sizes: "16x16", type: "image/png" },
      { url: "/icons/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/mark-64.png", sizes: "64x64", type: "image/png", rel: "shortcut icon" },
    ],
    shortcut: ["/icons/favicon-32.png"],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  openGraph: {
    type: "website",
    siteName: "VANTOR",
    title: TITLE,
    description: "Open-source procurement operating system. 10 products, one procurement graph, evidence-cited AI. Self-host free.",
    url: "/",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: "Open-source procurement operating system. 10 products, one procurement graph, evidence-cited AI.",
  },
  other: { "github:repo": "https://github.com/chandrahotha/Vantor" },
  formatDetection: { telephone: false, address: false, email: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#0A1931" },
    { media: "(prefers-color-scheme: dark)", color: "#0b101d" },
  ],
  colorScheme: "light dark",
};

const JSON_LD = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "SoftwareApplication",
      "@id": `${APP_URL}/#app`,
      name: "VANTOR",
      alternateName: "VANTOR Procurement OS",
      applicationCategory: "BusinessApplication",
      applicationSubCategory: "Procurement",
      operatingSystem: "Linux, macOS, Windows (Docker)",
      description:
        "Open-source procurement operating system unifying supplier intelligence, strategic sourcing, contracts, purchase orders, spend analytics and an evidence-cited AI copilot.",
      url: APP_URL,
      softwareVersion: "0.8.0",
      license: "https://www.gnu.org/licenses/agpl-3.0.html",
      author: { "@type": "Organization", name: "Digi Tracks", url: "https://github.com/chandrahotha" },
      codeRepository: "https://github.com/chandrahotha/Vantor",
      programmingLanguage: ["Python", "TypeScript", "SQL"],
      runtimePlatform: ["Docker", "PostgreSQL 16", "Redis", "Next.js 16", "FastAPI"],
      offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
      featureList: [
        "Supplier intelligence, scorecards and qualification",
        "RFQ, quotation comparison and award",
        "Contract lifecycle, obligations and 11-dimension matching",
        "Requisitions, purchase orders, receipts and three-way match",
        "Spend analytics, leakage, maverick detection and should-cost",
        "PO price intelligence and negotiation simulation",
        "Evidence-cited AI copilot with human-in-the-loop approvals",
        "Keycloak OIDC, Row Level Security tenancy and hash-chained audit",
      ],
    },
    {
      "@type": "Organization",
      "@id": `${APP_URL}/#org`,
      name: "Digi Tracks",
      url: "https://github.com/chandrahotha",
      contactPoint: { "@type": "ContactPoint", email: "digi.tracks@outlook.com", contactType: "customer support" },
    },
  ],
};

// Sets `data-theme` before the browser paints a single pixel.
//
// `data-palette` is server-rendered as the default so that token layer is
// active on the very first paint (see the comment below), but light/dark
// `data-theme` had no equivalent: it was only ever written inside
// `ThemeInit`'s `useEffect`, which runs *after* the first paint. Every visitor
// whose OS prefers dark mode, or who had previously chosen dark, was shown a
// flash of the light theme on every single page load and hard navigation
// before JS caught up and flipped it — the exact "visible flash" the palette
// attribute was deliberately server-rendered to avoid. A blocking inline
// script in `<head>` runs synchronously while the HTML is still parsing, so
// `data-theme` is correct before `<body>` ever paints. `ThemeInit`'s effect
// still runs on mount (so OS-preference changes keep being tracked live) but
// now starts from the right value instead of correcting it a frame late.
const THEME_INIT_SCRIPT = `(function(){try{var k="vantor.theme",s=localStorage.getItem(k),d=document.documentElement;d.dataset.theme=s==="light"||s==="dark"?s:(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");}catch(e){}})();`;

export default function Root({ children }: { children: React.ReactNode }) {
  return (
    // `data-palette` is server-rendered as the default so the token layer is
    // active on the very first paint. Without it the app would paint with the
    // un-bridged tokens and then re-paint once ThemeInit adopts the stored
    // choice — a visible flash for every user who chose a non-default palette.
    <html lang="en" data-palette="cobalt" className={`${inter.variable} ${jetbrains.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        <NextTopLoader color="var(--primary)" showSpinner={false} />
        <ThemeInit />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}