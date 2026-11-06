/**
 * The OIDC browser flow, asserted where it can be abused.
 *
 * This code did not exist until the `AUTH_MODE=oidc` deployment was found to
 * have no way to sign in at all. A login flow is not a place to ship untested:
 * every branch below is either a credential in a URL, a check that stops
 * somebody else's code being redeemed in this browser, or the claim mapping
 * that decides which tenant's data the session can reach.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setSession } from "./auth";
import {
  assertSecureIssuer,
  buildAuthorizeUrl,
  completeOidcSignIn,
  decodeClaims,
  oidcSession,
} from "./oidc";

const PROVIDER = {
  issuer: "https://idp.example.com/realms/vantor",
  clientId: "vantor-web",
  scope: "openid profile email",
  authorizationEndpoint: "https://idp.example.com/realms/vantor/protocol/openid-connect/auth",
  tokenEndpoint: "https://idp.example.com/realms/vantor/protocol/openid-connect/token",
  endSessionEndpoint: "https://idp.example.com/realms/vantor/protocol/openid-connect/logout",
};

/** A JWT-shaped string with the given payload. Signature is not real: nothing in
 *  the client verifies it, and the client must not start pretending to. */
function fakeJwt(payload: Record<string, unknown>): string {
  const b64 = (s: string) => btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${b64(JSON.stringify({ alg: "RS256", kid: "test" }))}.${b64(JSON.stringify(payload))}.sig`;
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("authorize request", () => {
  it("sends S256 PKCE, a state, and the registered callback origin", async () => {
    const url = new URL(
      await buildAuthorizeUrl(PROVIDER, {
        verifier: "a".repeat(43), state: "state-1", redirectUri: "https://app.example.com/auth/callback",
      }),
    );
    expect(url.origin).toBe("https://idp.example.com");
    const q = url.searchParams;
    expect(q.get("response_type")).toBe("code");
    expect(q.get("code_challenge_method")).toBe("S256");
    expect(q.get("client_id")).toBe("vantor-web");
    expect(q.get("state")).toBe("state-1");
    expect(q.get("redirect_uri")).toBe("https://app.example.com/auth/callback");
    // The challenge is the SHA-256 of the verifier, not the verifier itself.
    expect(q.get("code_challenge")).not.toBe("a".repeat(43));
    expect(q.get("code_challenge")).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });

  it("refuses a plaintext identity provider on a real host", () => {
    expect(() => assertSecureIssuer("http://idp.example.com/realms/vantor")).toThrow(/plaintext/i);
    // localhost is the one exception browsers make, and the dev stack needs it.
    expect(() => assertSecureIssuer("http://localhost:8080/realms/vantor")).not.toThrow();
  });
});

describe("callback", () => {
  /** Stash a verifier/state the way startOidcSignIn would, then hand the
   *  callback a query string. */
  function prime(state = "state-1", verifier = "verifier-value") {
    sessionStorage.setItem("vantor.oidc.verifier", verifier);
    sessionStorage.setItem("vantor.oidc.state", state);
  }

  it("refuses a state that does not match this browser's", async () => {
    prime("the-state-we-issued");
    await expect(completeOidcSignIn("code=abc&state=some-other-state", PROVIDER)).rejects.toThrow(/state/i);
  });

  it("refuses to run without a verifier, rather than sending a guess", async () => {
    prime();
    sessionStorage.removeItem("vantor.oidc.verifier");
    await expect(completeOidcSignIn("code=abc&state=state-1", PROVIDER)).rejects.toThrow(/verifier/i);
  });

  it("surfaces the IdP's own refusal instead of a generic failure", async () => {
    prime();
    await expect(completeOidcSignIn("error=access_denied&error_description=not+allowed", PROVIDER)).rejects.toThrow(
      /access_denied/,
    );
  });

  it("consumes the verifier even when the exchange fails", async () => {
    prime();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "invalid_grant" }), {
      status: 400, headers: { "Content-Type": "application/json" },
    })));
    await expect(completeOidcSignIn("code=used&state=state-1", PROVIDER)).rejects.toThrow(/invalid_grant/);
    // A code is single-use. Leaving the verifier behind invites a retry that
    // replays a dead code and reports the IdP as broken.
    expect(sessionStorage.getItem("vantor.oidc.verifier")).toBeNull();
  });

  it("exchanges the code with the verifier it kept", async () => {
    prime();
    const access = fakeJwt({
      iss: PROVIDER.issuer, aud: "vantor-web", sub: "user-1", tenant_id: "acme",
      realm_access: { roles: ["Buyer"] }, exp: Math.floor(Date.now() / 1000) + 300,
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      access_token: access, id_token: access, refresh_token: "rt-1", expires_in: 300,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const tokens = await completeOidcSignIn("code=fresh&state=state-1", PROVIDER);
    const body = new URLSearchParams((fetchMock.mock.calls[0] as [string, RequestInit])[1].body as string);
    expect(body.get("code_verifier")).toBe("verifier-value");
    expect(body.get("grant_type")).toBe("authorization_code");
    expect(tokens.accessToken).toBe(access);
    expect(tokens.refreshToken).toBe("rt-1");
  });
});

describe("session from claims", () => {
  it("takes the tenant from the token and unions both role sources", () => {
    const tokens = {
      accessToken: fakeJwt({
        tenant_id: "acme", name: "Ana Buyer",
        realm_access: { roles: ["Buyer"] },
        resource_access: { "vantor-web": { roles: ["Approver"] } },
      }),
      idToken: "", refreshToken: "rt-1", expiresAt: Date.now() + 300_000,
      claims: {
        tenant_id: "acme", name: "Ana Buyer",
        realm_access: { roles: ["Buyer"] },
        resource_access: { "vantor-web": { roles: ["Approver"] } },
      },
    };
    const session = oidcSession(tokens);
    expect(session.tenant).toBe("acme");
    expect(session.roles).toEqual(["Approver", "Buyer"]);
    expect(session.name).toBe("Ana Buyer");
    expect(session.provider).toBe("oidc");
  });

  it("refuses a token with no tenant, which is a realm mapper fault", () => {
    // The API answers 403 for the same token. Saying it at sign-in is the
    // difference between "the IdP is broken" and an empty dashboard.
    const tokens = {
      accessToken: fakeJwt({ sub: "x" }), idToken: "", refreshToken: "",
      expiresAt: Date.now() + 300_000, claims: { sub: "x" },
    };
    expect(() => oidcSession(tokens)).toThrow(/no tenant/i);
  });

  it("keeps the refresh token out of localStorage", () => {
    setSession({
      token: "access-1", name: "Ana", tenant: "acme", roles: ["Buyer"],
      expiresAt: Date.now() + 300_000, provider: "oidc", refreshToken: "rt-1",
    });
    const stored = JSON.parse(localStorage.getItem("vantor.session") || "{}");
    expect(stored.token).toBe("access-1");
    expect(stored.refreshToken ?? "").toBe("");
    expect(localStorage.getItem("vantor.session")).not.toContain("rt-1");
    // ...and it is still available to this tab for renewal.
    expect(sessionStorage.getItem("vantor.session.refresh")).toBe("rt-1");
  });
});

describe("claim decoding", () => {
  it("reads the payload without pretending to verify it", () => {
    expect(decodeClaims(fakeJwt({ tenant_id: "acme" })).tenant_id).toBe("acme");
    expect(() => decodeClaims("not-a-jwt")).toThrow(/not a JWT/);
  });
});
