import type { MetadataRoute } from "next";

const routes = ["", "/suppliers", "/rfqs", "/contracts", "/orders", "/spend", "/documents", "/copilot", "/notifications"];

// Fixed date keeps builds byte-identical (cacheable, diffable).
const LAST_MODIFIED = new Date("2026-09-26T00:00:00Z");

export default function sitemap(): MetadataRoute.Sitemap {
  const base = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";
  return routes.map((r) => ({ url: `${base}${r || "/"}`, lastModified: LAST_MODIFIED, changeFrequency: "weekly", priority: r === "" ? 1 : 0.7 }));
}
