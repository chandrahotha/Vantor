import type { MetadataRoute } from "next";

/** Honest robots policy.
 *
 *  Every route in this app is behind Keycloak OIDC (`onLoad: "login-required"`),
 *  so allowing crawlers to walk the site buys nothing: the only thing indexable
 *  is the identity-provider redirect. The genuinely discoverable surfaces for
 *  this product are the documentation site and the GitHub repository, and both
 *  are named here so crawlers are pointed at them instead of at a login wall.
 */
export default function robots(): MetadataRoute.Robots {
  const base = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        // The API lives on :8000 with its own auth, but disallow it here too in
        // case it is ever reverse-proxied under this origin.
        disallow: ["/api/", "/api/v1/"],
      },
    ],
    sitemap: `${base}/sitemap.xml`,
    host: base,
  };
}
