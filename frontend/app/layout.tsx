import type { Metadata, Viewport } from "next";
import "./globals.css";

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
    "procurement software",
    "procurement operating system",
    "open source procurement",
    "supplier management",
    "supplier risk",
    "strategic sourcing",
    "RFQ",
    "RFP",
    "quotation comparison",
    "contract lifecycle management",
    "CLM",
    "purchase order",
    "purchase requisition",
    "three way match",
    "spend analytics",
    "spend intelligence",
    "should-cost model",
    "maverick spend",
    "savings tracking",
    "procurement approval workflow",
    "supplier onboarding",
    "supplier qualification",
    "negotiation simulator",
    "procurement AI copilot",
    "human in the loop AI",
    "Keycloak OIDC",
    "Row Level Security",
    "FastAPI",
    "Next.js",
    "Postgres",
    "AGPL-3.0",
    "self-hosted",
    "open source ERP",
    "Digi Tracks",
  ],
  // Honest indexing posture: every route is behind Keycloak OIDC, so a crawler
  // can only ever see the identity-provider redirect. Claiming `index: true`
  // invited crawlers to index a login wall and nothing else. The discoverable
  // surfaces for this product are the docs site and the GitHub repository;
  // the app origin is marked noindex but social crawlers still fetch the OG card.
  robots: { index: false, follow: false, nocache: true, googleBot: { index: false, follow: false } },
  alternates: { canonical: "/" },
  manifest: "/manifest.webmanifest",
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
  other: {
    "github:repo": "https://github.com/chandrahotha/Vantor",
  },
  formatDetection: { telephone: false, address: false, email: false },
};

/** `themeColor` moved to the `viewport` export in Next 14+; keeping it here
 *  silently drops it from the generated HTML. */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0A1931",
  colorScheme: "light",
};

/** Structured data so search engines and AI crawlers can identify the product
 *  without scraping the login-walled UI. `SoftwareApplication` with
 *  `offers: 0` is the honest shape: it is free and self-hosted, not a SaaS
 *  with a price. */
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
    <html lang="en">
      <body>
        <script
          type="application/ld+json"
          // Static, developer-authored JSON-LD — no user input reaches this string.
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
        {children}
      </body>
    </html>
  );
}
