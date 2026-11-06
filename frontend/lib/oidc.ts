/**
 * OIDC sign-in for the web app: authorization code + PKCE, no client secret.
 *
 * This file did not exist until now, which is the reason `AUTH_MODE=oidc` — the
 * mode `.env.example` ships, the mode `docker compose up` provisions a whole
 * Keycloak container for — produced a sign-in screen that could not sign in.
 * The button POSTed to `/auth/session`, that route answers 404
 * `LOCAL_AUTH_DISABLED` in OIDC mode with the message "Sign in through it", and
 * there was no "it" anywhere in the client: no authorize redirect, no callback
 * route, no token exchange. CI could not see it because the e2e job starts the
 * API with `AUTH_MODE=local`.
 *
 * Why PKCE and no secret: `vantor-web` is provisioned as a public client
 * (`deploy/keycloak/realm-vantor.json`, `publicClient: true`,
 * `pkce.code.challenge.method: S256`). A browser cannot hold a secret — anything
 * it ships with is in the bundle — so the flow that is correct for an SPA is
 * authorization code with PKCE, where the code is worthless without the
 * verifier that never left this tab.
 *
 * The token this produces is used directly as the app's bearer credential. It
 * carries `iss`, `aud`, `sub`, `tenant_id` and the realm/role mappings, which is
 * exactly what `core/security.py` verifies on every request; the API never
 * accepts a locally-minted session in this mode, so there is no second token to
 * manage and no proxy that could forge one.
 */
import type { AuthConfig, Session } from "./auth";

/** Where the IdP sends the browser back to. Must be listed on the Keycloak
 *  client — `WEB_ORIGINS` in .env drives that list through keycloak-init. */
export const OIDC_CALLBACK_PATH = "/auth/callback";

const VERIFIER_KEY = "vantor.oidc.verifier";
const STATE_KEY = "vantor.oidc.state";
const RETURN_KEY = "vantor.oidc.return";
/** Keycloak's own session-staleness parameter; keeps the flow usable when the
 *  operator is mid-way through switching identity. */
const MAX_AGE_S = 3600;

export type OidcTokens = {
  accessToken: string;
  idToken: string;
  refreshToken: string;
  /** Epoch milliseconds. */
  expiresAt: number;
  claims: Record<string, unknown>;
};

function base64Url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomUrlSafe(length: number): string {
  const buf = new Uint8Array(length);
  crypto.getRandomValues(buf);
  return base64Url(buf);
}

async function sha256Base64Url(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return base64Url(new Uint8Array(digest));
}

/** Refuse to send an authorization code anywhere but a secure origin, with the
 *  one exception every browser makes for a local machine. A plaintext IdP on a
 *  network is a credential leak with extra steps. */
export function assertSecureIssuer(issuer: string): void {
  let url: URL;
  try {
    url = new URL(issuer);
  } catch {
    throw new Error(`The identity provider issuer is not a valid URL: ${issuer}`);
  }
  const local = url.hostname === "localhost" || url.hostname === "127.0.0.1" || url.hostname === "::1";
  if (url.protocol !== "https:" && !local) {
    throw new Error(
      `Refusing to sign in through ${issuer}: the identity provider is reachable only over ` +
      "plaintext, and an authorization code sent in the clear is a credential.",
    );
  }
}

export function callbackUrl(): string {
  return `${window.location.origin}${OIDC_CALLBACK_PATH}`;
}

/** The authorize URL, built from parts so it can be asserted without navigating.
 *  Every parameter here is load-bearing: `S256` is what the realm's
 *  `pkce.code.challenge.method` demands, and `state` is the CSRF check. */
export function buildAuthorizeUrl(
  provider: NonNullable<AuthConfig["oidcProvider"]>,
  opts: { verifier: string; state: string; redirectUri: string; scope?: string },
): Promise<string> {
  return sha256Base64Url(opts.verifier).then((challenge) => {
    const params = new URLSearchParams({
      client_id: provider.clientId,
      redirect_uri: opts.redirectUri,
      response_type: "code",
      scope: opts.scope || provider.scope || "openid profile email",
      state: opts.state,
      code_challenge: challenge,
      code_challenge_method: "S256",
      max_age: String(MAX_AGE_S),
    });
    return `${provider.authorizationEndpoint}?${params.toString()}`;
  });
}

/** Build the authorize URL and stash the verifier/state for the callback.
 *
 * `sessionStorage` rather than a module variable on purpose: the redirect to the
 * IdP tears this document down, and a second tab must not be able to consume the
 * first tab's verifier.
 */
export async function startOidcSignIn(
  config: AuthConfig,
  redirectTo = "/",
): Promise<void> {
  const provider = config.oidcProvider;
  if (!provider?.authorizationEndpoint || !provider.clientId) {
    throw new Error("This deployment does not offer identity-provider sign-in.");
  }
  assertSecureIssuer(provider.issuer);
  // Checked again as a full URL, because this is what the browser is handed the
  // code to. A relative value here would turn the login into an internal
  // redirect and leak the authorization code into our own query string.
  if (!/^https?:\/\//i.test(provider.authorizationEndpoint)) {
    throw new Error(`The identity provider's authorization endpoint is not an absolute URL: ${provider.authorizationEndpoint}`);
  }

  const verifier = randomUrlSafe(32);
  const state = randomUrlSafe(16);

  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(RETURN_KEY, redirectTo);

  const url = await buildAuthorizeUrl(provider, {
    verifier, state, redirectUri: callbackUrl(), scope: provider.scope,
  });
  // A full-window navigation, not a router push: the destination is the identity
  // provider's origin, which is outside this app, and the absolute-URL check
  // above is what makes a relative destination impossible here.
  window.location.assign(url);
}

/** Read the JWT payload for display only.
 *
 * The signature is *not* checked here and must not be trusted if it were: the
 * API verifies every token against the issuer's JWKS on every request. This
 * exists so the shell can show a name and a tenant before the first API call
 * returns, and nothing in the UI may make a permission decision from it.
 */
export function decodeClaims(jwt: string): Record<string, unknown> {
  const payload = jwt.split(".")[1];
  if (!payload) throw new Error("The identity provider returned a token that is not a JWT.");
  const json = payload.replace(/-/g, "+").replace(/_/g, "/");
  const padded = json + "=".repeat((4 - (json.length % 4)) % 4);
  return JSON.parse(atob(padded)) as Record<string, unknown>;
}

function takeStored(key: string): string {
  const value = sessionStorage.getItem(key) ?? "";
  sessionStorage.removeItem(key);
  return value;
}

/** Exchange the code for tokens. Clears the stash even on failure: a verifier is
 *  single-use, and leaving it behind would let a retry replay a dead code.
 *
 *  `provider` is a parameter, not a fetch inside here. This function's whole job
 *  is handling a credential that arrived in the URL; an undeclared network call
 *  in the middle of it makes its failure modes someone else's, and made it
 *  untestable without mocking two different endpoints through one seam.
 */
export async function completeOidcSignIn(
  search: string,
  provider: NonNullable<AuthConfig["oidcProvider"]>,
): Promise<OidcTokens> {
  const params = new URLSearchParams(search);
  const error = params.get("error");
  const verifier = takeStored(VERIFIER_KEY);
  const expectedState = takeStored(STATE_KEY);

  if (error) {
    throw new Error(`The identity provider refused the sign-in: ${error} ${params.get("error_description") ?? ""}`.trim());
  }
  const code = params.get("code");
  if (!code) throw new Error("The identity provider redirected back without an authorization code.");
  if (!verifier) {

    throw new Error(
      "This tab has no PKCE verifier to finish the sign-in with — the flow was started in a " +
      "different tab, or the page was reloaded between the redirect and this callback. Open the " +
      "app and sign in again.",
    );
  }
  const state = params.get("state");
  if (!expectedState || state !== expectedState) {
    // The state parameter is what makes a code injected by another request
    // useless; a mismatch is the CSRF signal, not a nuisance to route around.
    throw new Error("Sign-in was rejected: the state returned by the identity provider does not match this browser's.");
  }

  if (!provider?.tokenEndpoint || !provider.clientId) {
    throw new Error("This deployment does not offer identity-provider sign-in.");
  }

  let res: Response;
  try {
    res = await fetch(provider.tokenEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: provider.clientId,
        code,
        redirect_uri: callbackUrl(),
        code_verifier: verifier,
      }),
    });
  } catch {
    throw new Error(`Could not reach the identity provider at ${provider.tokenEndpoint}.`);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(body?.error_description || body?.error || `The identity provider refused the code exchange (${res.status}).`);
  }
  if (!body?.access_token) throw new Error("The identity provider returned no access token.");

  const claims = decodeClaims(body.access_token as string);
  return {
    accessToken: body.access_token,
    idToken: body.id_token ?? "",
    refreshToken: body.refresh_token ?? "",
    expiresAt: Date.now() + (Number(body.expires_in ?? 300) * 1000),
    claims,
  };
}

/** Refresh with the stored refresh token. Returns null when the IdP declines,
 *  which the caller treats as "signed out" rather than "keep trying". */
export async function refreshOidc(
  refreshToken: string,
  provider: NonNullable<AuthConfig["oidcProvider"]>,
): Promise<OidcTokens | null> {
  let res: Response;
  try {
    res = await fetch(provider.tokenEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        client_id: provider.clientId,
        refresh_token: refreshToken,
      }),
    });
  } catch {
    return null;
  }
  if (!res.ok) return null;
  const body = await res.json().catch(() => null);
  if (!body?.access_token) return null;
  return {
    accessToken: body.access_token,
    idToken: body.id_token ?? "",
    refreshToken: body.refresh_token ?? refreshToken,
    expiresAt: Date.now() + (Number(body.expires_in ?? 300) * 1000),
    claims: decodeClaims(body.access_token as string),
  };
}

export function oidcReturnPath(): string {
  return takeStored(RETURN_KEY) || "/";
}

/** Turn IdP claims into the session shape the app already uses.
 *
 *  `tenant_id` is not optional here and the API enforces the same rule
 *  (`core/security.py` refuses a token with no tenant with 403): a realm mapper
 *  that does not emit it produces a signed-in user who can see nothing, which
 *  is a configuration fault and must be said as one rather than rendered as an
 *  empty dashboard.
 */
export function oidcSession(tokens: OidcTokens): Session {
  const c = tokens.claims;
  const roles = new Set<string>();
  const realm = (c.realm_access as { roles?: string[] } | undefined)?.roles;
  for (const r of realm ?? []) roles.add(r);
  const resourceAccess = (c.resource_access as Record<string, { roles?: string[] }> | undefined) ?? {};
  for (const entry of Object.values(resourceAccess)) for (const r of entry.roles ?? []) roles.add(r);

  const tenant = String(c.tenant_id ?? c.org_id ?? "");
  if (!tenant) {
    throw new Error(
      "Signed in, but the identity provider issued a token with no tenant. The realm's tenant " +
      "claim mapper is not configured for this client, so the API will refuse every request.",
    );
  }

  const name = String(c.name ?? "") ||
    String((c.preferred_username as string) ?? "") ||
    String(c.email ?? "") ||
    "VANTOR user";

  return {
    token: tokens.accessToken,
    name,
    tenant,
    roles: [...roles].sort(),
    expiresAt: tokens.expiresAt,
    persona: "",
    provider: "oidc",
    refreshToken: tokens.refreshToken,
  };
}
