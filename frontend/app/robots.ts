import type { MetadataRoute } from "next";

/** Honest robots policy.
 *
 *  Every route in this app is behind Keycloak OIDC, so there is nothing here for
 *  a crawler to index: the only thing it can reach is the identity-provider
 *  redirect. This file used to say exactly that and then went on to `allow: "/"`
 *  and publish a sitemap of thirteen login-walled routes — including /copilot.
 *  The stated intent and the emitted policy contradicted each other inside one
 *  file, which is worse than either alone: a reader would trust the comment.
 *
 *  So the policy now matches the comment. The genuinely discoverable surfaces
 *  for this product are the documentation site and the GitHub repository, and
 *  neither is served from this origin, so neither is advertised here.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        // Nothing under this origin is public. `/api/` is called out separately
        // in case the API is ever reverse-proxied here, where it has its own auth.
        disallow: ["/", "/api/", "/api/v1/"],
      },
    ],
  };
}
