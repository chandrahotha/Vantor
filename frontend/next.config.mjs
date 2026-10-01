/** @type {import('next').NextConfig} */

/**
 * Security headers for the *web app's own* responses.
 *
 * VNT-031, residue. The API sets a strict CSP, but the API is a different origin
 * from the app: a Content-Security-Policy delivered by the API governs documents
 * the API serves, and the pages a user actually reads are served by Next. So the
 * policy that protects the application UI was on the wrong host, and the app was
 * running with no CSP at all.
 *
 * Two deliberate differences from the API's policy, both because this host serves
 * the document rather than a JSON body:
 *
 * - **`'unsafe-inline'` for styles is unavoidable here.** Next inlines the CSS
 *   needed for the first paint into the document; a nonce cannot reach a
 *   stylesheet Next generates at build time. Scripts are the injection surface
 *   that matters, and those are held to a nonce with no `unsafe-inline`.
 * - **No `strict-dynamic`.** It is correct alongside a nonce, but Next's own
 *   bootstrap script is injected without one, and adding the directive would
 *   make the app depend on a nonce it does not control.
 *
 * Everything here is static, so it can live in `headers()` and be correct on the
 * very first response - a per-request nonce in middleware would have to be
 * threaded into the document as well, which is a much larger change for a
 * marginal gain on a page with no user-generated markup.
 *
 * The frame, referrer and content-type policies are the parts that do most of
 * the work in practice: this app never needs to be framed, and it never sends a
 * referrer to a third party.
 */
/** Origins this app is allowed to talk to, derived from configuration.
 *
 *  Hardcoding `http://localhost:8000` would have made the policy a lie in every
 *  deployment that is not on localhost: the browser blocks the API call and the
 *  app looks broken with no indication why. Derived from the same env the app
 *  already uses, so a deployment that moves its API moves its CSP with it.
 */
/** Where the browser sends API calls.
 *
 *  Empty is meaningful and is what the single-container image uses: the web app
 *  then calls `/api/...` on its own origin and Next proxies it to the API in
 *  the same container (see `rewrites` below). That keeps the image free of any
 *  build-time knowledge of the host it will be deployed to — baking
 *  `http://localhost:8000` into the bundle is what makes an image that works
 *  only on the machine that built it.
 */
const RAW_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SAME_ORIGIN_API = RAW_API.trim() === "";
const API_ORIGIN = SAME_ORIGIN_API ? "" : new URL(RAW_API).origin;
/** The in-container API address, used only by the server-side proxy. */
const INTERNAL_API = process.env.INTERNAL_API_URL || "";
const APP_ORIGIN = new URL(
  process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",
).origin;
const IS_HTTPS = APP_ORIGIN.startsWith("https://");
const IS_DEV = process.env.NODE_ENV !== "production";

const csp = [
  "default-src 'self'",
  // Next injects an inline bootstrap script; without 'unsafe-inline' the app
  // would not boot. React devtools and Turbopack require 'unsafe-eval' in dev mode
  // for sourcemaps and callstack reconstruction.
  `script-src 'self' 'unsafe-inline'${IS_DEV ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  // The API and the identity provider are the only other origins this app talks
  // to. `connect-src` covers fetch/XHR; `form-action` covers a stray form post.
  // The API is the only other origin this app talks to. The identity
  // provider used to be listed here too; sign-in is now served by the API
  // itself, so naming a Keycloak host would widen the policy for nothing.
  `connect-src 'self'${API_ORIGIN ? ` ${API_ORIGIN}` : ""}`,
  // Nothing is framed any more: the silent-check-sso iframe went with Keycloak.
  "frame-src 'none'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  // Only meaningful over TLS, and only safe to ask for over TLS. Sending it on
  // an http origin is ignored by browsers, but it would be a false claim in the
  // configuration, so it is conditional on the app actually being served over
  // https rather than emitted unconditionally with a reassuring comment.
  ...(IS_HTTPS ? ["upgrade-insecure-requests"] : []),
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
  ...(IS_HTTPS
    ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }]
    : []),
];

const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  env: {
    NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",
    // `??`, not `||`: an explicitly empty NEXT_PUBLIC_API_URL means same-origin
    // (see RAW_API above) and must reach the client bundle as "", not as the
    // hardcoded dev fallback. `||` treats "" as unset because it is falsy, so
    // this used to rewrite the single-container image's deliberate same-origin
    // setting back into `http://localhost:8000` — a host unreachable from the
    // browser outside the machine that built the image, which made every API
    // call from the UI fail on an otherwise-healthy deployment.
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
  /** Same-origin API proxy for the single-container image.
   *
   *  Only active when `INTERNAL_API_URL` is set, so the Compose stack — where
   *  the browser talks to the API directly on its own host — is untouched.
   */
  async rewrites() {
    if (!INTERNAL_API) return [];
    return [{ source: "/api/:path*", destination: `${INTERNAL_API}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};
export default nextConfig;
