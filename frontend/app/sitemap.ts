import type { MetadataRoute } from "next";

const ROUTES: { path: string; priority: number; changeFrequency: "always" | "hourly" | "daily" | "weekly" | "monthly" | "yearly" | "never" }[] = [
  { path: "", priority: 1, changeFrequency: "daily" },
  { path: "/suppliers", priority: 0.8, changeFrequency: "daily" },
  { path: "/requisitions", priority: 0.7, changeFrequency: "daily" },
  { path: "/rfqs", priority: 0.8, changeFrequency: "daily" },
  { path: "/orders", priority: 0.8, changeFrequency: "daily" },
  { path: "/contracts", priority: 0.7, changeFrequency: "weekly" },
  { path: "/spend", priority: 0.7, changeFrequency: "weekly" },
  { path: "/documents", priority: 0.6, changeFrequency: "weekly" },
  { path: "/governance", priority: 0.6, changeFrequency: "daily" },
  { path: "/notifications", priority: 0.4, changeFrequency: "hourly" },
  { path: "/copilot", priority: 0.6, changeFrequency: "weekly" },
];

/** Generated per build rather than hardcoded.
 *  A frozen `lastModified` is a lie to crawlers â€” it tells them a page changed
 *  on a date it did not. `output: "standalone"` builds are immutable, so the
 *  build time is the honest "content as of" stamp. */
export default function sitemap(): MetadataRoute.Sitemap {
  const base = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";
  const lastModified = new Date();
  return ROUTES.map((r) => ({
    url: `${base}${r.path || "/"}`,
    lastModified,
    changeFrequency: r.changeFrequency,
    priority: r.priority,
  }));
}
