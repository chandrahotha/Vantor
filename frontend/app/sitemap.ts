import type { MetadataRoute } from "next";

/** Route inventory, used for build-time completeness checks.
 *
 *  This is NOT published as a crawlable sitemap: every route here is behind
 *  Keycloak OIDC, so there is nothing indexable on this origin, and `robots.ts`
 *  disallows all of it. A `lastModified` stamped at build time is only honest
 *  because `output: "standalone"` builds are immutable — keep it that way, or
 *  this file has to start serving a real per-page date. */
export const ROUTES: { path: string; priority: number; changeFrequency: "always" | "hourly" | "daily" | "weekly" | "monthly" | "yearly" | "never" }[] = [
  { path: "", priority: 1, changeFrequency: "daily" },
  { path: "/suppliers", priority: 0.8, changeFrequency: "daily" },
  { path: "/requisitions", priority: 0.7, changeFrequency: "daily" },
  { path: "/rfqs", priority: 0.8, changeFrequency: "daily" },
  { path: "/orders", priority: 0.8, changeFrequency: "daily" },
  { path: "/contracts", priority: 0.7, changeFrequency: "weekly" },
  { path: "/spend", priority: 0.7, changeFrequency: "weekly" },
  { path: "/integrations", priority: 0.6, changeFrequency: "weekly" },
  { path: "/negosim", priority: 0.5, changeFrequency: "monthly" },
  { path: "/documents", priority: 0.6, changeFrequency: "weekly" },
  { path: "/governance", priority: 0.6, changeFrequency: "daily" },
  { path: "/notifications", priority: 0.4, changeFrequency: "hourly" },
  { path: "/copilot", priority: 0.6, changeFrequency: "weekly" },
];

/** Emits an empty sitemap on purpose — see the note on ROUTES. */
export default function sitemap(): MetadataRoute.Sitemap {
  return [];
}
