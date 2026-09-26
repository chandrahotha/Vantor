import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import ThemeInit from "../components/ThemeInit";

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
    "FastAPI", "Next.js", "Postgres", "AGPL-3.0", "self-hosted", "open source ERP", "Digi Tracks",
  ],
  // Honest indexing posture: every route is behind Keycloak OIDC, so a crawler
  // can only ever see the identity-provider redirect. The discoverable surfaces
  // for this product are the docs site and the GitHub repository.
  robots: { index: false, follow: false, nocache: true, googleBot: { index: false, follow: false } },
  alternates: { canonical: "/" },
  manifest: "/manifest.webmanifest",
  // Canonical marks: vantor-icon-source.png (glossy V+orbit squircle) is the one
  // brand — rasterized into public/icons/. No generated letter-marks anywhere.
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

export default function Root({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable}`} suppressHydrationWarning>
      <body>
        <ThemeInit />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
        {children}
      </body>
    </html>
  );
}
