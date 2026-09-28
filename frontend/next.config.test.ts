import { describe, expect, it, vi } from "vitest";

/**
 * VNT-031, residue: the API had a strict CSP and the web app had none.
 *
 * A Content-Security-Policy delivered by the API governs documents the *API*
 * serves. The pages a user actually reads are served by Next, from a different
 * origin, so the policy that was supposed to protect the application UI was on
 * the wrong host entirely. This asserts the app's own responses carry one.
 *
 * The headers are read from `next.config.mjs` as a module, because asserting
 * against a running server is a browser test and there is no browser here. The
 * point being guarded is that the policy exists, is derived from configuration
 * rather than hardcoded, and does not block the app's own API.
 */

async function loadConfig(env: Record<string, string | undefined> = {}) {
  vi.resetModules();
  for (const [k, v] of Object.entries(env)) process.env[k] = v;
  const mod = await import("./next.config.mjs");
  return mod.default;
}

type Header = { key: string; value: string };

async function headersFor(env: Record<string, string | undefined> = {}): Promise<Header[]> {
  const config = await loadConfig(env);
  const routes = (await config.headers()) as Array<{ source: string; headers: Header[] }>;
  const route = routes.find((r) => r.source === "/:path*");
  if (!route) {
    throw new Error("next.config declares no headers for /:path* — the app would be unprotected");
  }
  return route.headers;
}

function headerValue(headers: Header[], key: string) {
  return headers.find((h) => h.key === key)?.value;
}

function cspOf(headers: Header[]): string {
  const csp = headerValue(headers, "Content-Security-Policy");
  if (!csp) throw new Error("no Content-Security-Policy on the app's own responses");
  return csp;
}

describe("next.config security headers", () => {
  it("puts a content security policy on the app's own responses", async () => {
    // The API's CSP governs documents the API serves. The pages a user reads are
    // served by Next, from a different origin, so the policy meant to protect
    // the application UI was on the wrong host.
    expect(cspOf(await headersFor())).toBeTruthy();
  });

  it("denies framing, object embedding and base-tag hijacking", async () => {
    const headers = await headersFor();
    const csp = cspOf(headers);
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");
    expect(headerValue(headers, "X-Frame-Options")).toBe("DENY");
    expect(headerValue(headers, "X-Content-Type-Options")).toBe("nosniff");
  });

  it("derives the allowed origins from configuration rather than hardcoding them", async () => {
    // A hardcoded `http://localhost:8000` makes the policy a lie in every
    // deployment that is not on localhost: the browser blocks the API call and
    // the app looks broken with no indication why.
    const csp = cspOf(
      await headersFor({
        NEXT_PUBLIC_API_URL: "https://api.example.test",
        NEXT_PUBLIC_KEYCLOAK_URL: "https://id.example.test",
      }),
    );
    expect(csp).toContain("https://api.example.test");
    expect(csp).toContain("https://id.example.test");
    expect(csp).not.toContain("localhost:8000");
  });

  it("allows the app's own origin so it can load at all", async () => {
    const csp = cspOf(await headersFor());
    expect(csp).toContain("default-src 'self'");
    expect(csp).toMatch(/connect-src[^;]*'self'/);
  });

  it("does not claim HSTS while the app is served over http", async () => {
    // Sent over http it is ignored by browsers, so emitting it would be a false
    // claim in the configuration rather than a protection.
    const headers = await headersFor({ NEXT_PUBLIC_APP_URL: "http://localhost:3000" });
    expect(headerValue(headers, "Strict-Transport-Security")).toBeUndefined();
    expect(cspOf(headers)).not.toContain("upgrade-insecure-requests");
  });

  it("does claim HSTS once the app is served over https", async () => {
    const headers = await headersFor({ NEXT_PUBLIC_APP_URL: "https://vantor.example" });
    expect(headerValue(headers, "Strict-Transport-Security")).toContain("max-age=");
    expect(cspOf(headers)).toContain("upgrade-insecure-requests");
  });

  it("sends no referrer to third parties", async () => {
    const headers = await headersFor();
    expect(headerValue(headers, "Referrer-Policy")).toBe("no-referrer");
    expect(headerValue(headers, "Permissions-Policy")).toContain("camera=()");
  });
});
