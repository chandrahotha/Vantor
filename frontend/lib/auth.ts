/** Local, passwordless sessions.
 *
 * What changed and why
 * --------------------
 * This module used to wrap keycloak-js. Every route sat behind it, so the
 * product could not be opened without a Keycloak server: with none running,
 * "Sign in" navigated the browser to `localhost:8080` and the user got
 * `ERR_CONNECTION_REFUSED`. Worse, `keepFresh` re-checked the token every 45
 * seconds against that same unreachable server and ended the session when the
 * check failed — which is why switching to another window and back dropped the
 * app onto the sign-in screen: the interval had fired while it was in the
 * background.
 *
 * A session now comes from the API itself. `POST /api/v1/auth/session` returns
 * a real RS256 token carrying a tenant, an expiry and a role set, signed by a
 * key the API holds. The client is not trusted to invent one — it cannot, and
 * `getSession()` still returns `null` until the server has answered.
 *
 * It is passwordless by design: the server hands a session to whoever asks.
 * That is the documented trade for a deployment with no identity service — see
 * `backend/app/core/localauth.py`. It means anyone who can reach the app is the
 * operator, so such a deployment does not belong on an untrusted network.
 *
 * The token is persisted in `localStorage`. The old module refused to do that
 * on the grounds that a five-minute access token goes stale; these are
 * twelve-hour tokens issued by the same origin, and *not* persisting them is
 * what made every reload and every Fast Refresh throw the user back to the
 * sign-in screen. The value stored is exactly what the server issued — the
 * client cannot forge one that the API will accept.
 */

// `??`, not `||`: an explicitly empty NEXT_PUBLIC_API_URL means same-origin
// (the single-container image), and "" is falsy, so `||` would silently
// replace it with the dev fallback and send every request to an address the
// browser cannot reach outside the machine that built the image.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const STORAGE_KEY = "vantor.session";
/** Re-issue this far ahead of expiry, so a long-lived tab never blocks on it. */
const RENEW_BEFORE_MS = 30 * 60 * 1000;

export type Session = {
  token: string;
  name: string;
  tenant: string;
  roles: string[];
  /** Epoch milliseconds. */
  expiresAt: number;
  /** Local-auth persona key (e.g. "approver"), empty for an OIDC session. */
  persona?: string;
  /** Which side issued this token. Changes what a renewal attempt does. */
  provider?: "local" | "oidc";
  /** OIDC refresh token. Deliberately not persisted with the rest — see
   *  `setSession`. */
  refreshToken?: string;
};

/** Where the OIDC refresh token lives: this tab only.
 *
 *  A refresh token is the credential that can mint new access tokens for as long
 *  as the IdP session lasts — hours to days, versus the ~5 minutes an access
 *  token is good for. Keeping it in `sessionStorage` means it dies with the tab
 *  and is not readable by anything that survives a restart, while the short-lived
 *  access token still persists so a reload does not force a full re-auth.
 *  The remaining XSS exposure is real and is documented as such in
 *  docs/04-security/architecture.md; this narrows it, it does not close it.
 */
const REFRESH_KEY = "vantor.session.refresh";

type Listener = (s: Session | null) => void;

let current: Session | null = null;
const listeners = new Set<Listener>();

export function getSession(): Session | null {
  return current;
}

export function setSession(s: Session | null): void {
  current = s;
  try {
    if (s) {
      // Persist everything except the long-lived credential, then put that in
      // per-tab storage. `JSON.parse(JSON.stringify())` is not used: the object
      // is shallow and plain, and deleting a key from a copy keeps the caller's
      // session object intact.
      const { refreshToken, ...persist } = s;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(persist));
      if (refreshToken) sessionStorage.setItem(REFRESH_KEY, refreshToken);
      else sessionStorage.removeItem(REFRESH_KEY);
    } else {
      localStorage.removeItem(STORAGE_KEY);
      sessionStorage.removeItem(REFRESH_KEY);
    }
  } catch {
    // Private mode, or storage disabled. The session still works for this tab;
    // it just will not survive a reload.
  }
  for (const l of listeners) l(s);
}

export function subscribeSession(l: Listener): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

function isLive(s: Session | null): s is Session {
  return !!s && typeof s.token === "string" && s.token.length > 0 && s.expiresAt > Date.now();
}

/** Re-adopt a stored session, or `null` if there is none or it has expired.
 *
 *  Never invents a session: an expired or malformed entry is discarded rather
 *  than repaired, because a token the API will reject is worse than no token —
 *  it produces a UI that looks signed in and 401s on every panel.
 */
export function restoreSession(): Session | null {
  if (current) return current;
  try {
    if (typeof window === "undefined") return null;
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    if (!isLive(parsed)) {
      localStorage.removeItem(STORAGE_KEY);
      sessionStorage.removeItem(REFRESH_KEY);
      return null;
    }
    // The refresh token was deliberately kept out of `localStorage`; re-adopt it
    // for this tab, and if it is gone (new tab, or the tab was closed) fall back
    // to the access token, which still works until it expires.
    const refreshToken = sessionStorage.getItem(REFRESH_KEY) ?? parsed.refreshToken ?? "";
    current = refreshToken ? { ...parsed, refreshToken } : parsed;
    for (const l of listeners) l(parsed);
    return parsed;
  } catch {
    return null;
  }
}

export type OidcProviderInfo = {
  issuer: string;
  clientId: string;
  scope: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  endSessionEndpoint: string;
};

export type AuthConfig = {
  local: boolean;
  oidc: boolean;
  productName: string;
  /** Present only when the deployment actually verifies against an IdP. */
  oidcProvider?: OidcProviderInfo | null;
};

/** Ask the server how sign-in works here.
 *
 *  Network failure is reported as a failure. The previous version let
 *  `fetch`/`res.json()` throw a bare `TypeError: Failed to fetch` out of this
 *  function, which is the one error a UI cannot show usefully — and it was
 *  masked for as long as it took because nothing called it. `signIn()` has
 *  always named the address it tried; this now matches it.
 */
export async function fetchAuthConfig(signal?: AbortSignal): Promise<AuthConfig> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/auth/config`, { signal });
  } catch {
    throw new Error(
      `Could not reach the VANTOR API at ${API_URL} to ask how sign-in works. Start the backend, or set NEXT_PUBLIC_API_URL to where it is running.`,
    );
  }
  if (!res.ok) throw new Error(`The API answered ${res.status} when asked how to sign in.`);
  const body = await res.json().catch(() => null);
  const data = body?.data;
  if (!data || typeof data.local !== "boolean" || typeof data.oidc !== "boolean") {
    throw new Error("The API returned a sign-in configuration that is not in the expected shape.");
  }
  return data as AuthConfig;
}

/** Renew an OIDC session with its refresh token. Returns true when a new token
 *  is installed.
 *
 *  Local sessions have nothing to refresh — `POST /auth/session` is re-called —
 *  so this is the OIDC half of the same contract `api()` expects from its
 *  refresh hook: true means "retry the request", false means "the caller is
 *  signed out". It used to be that *no* refresh existed (`setRefreshFn(async ()
 *  => false)`), which is fine for local and wrong for an IdP token that expires
 *  on a five-minute clock while the user is mid-form.
 *
 *  Dynamic import, not a top-level one: `lib/oidc.ts` reads `AuthConfig` and
 *  `fetchAuthConfig` from here, and a static cycle between the two would make
 *  module initialisation order matter for no reason.
 */
export async function refreshOidcSession(): Promise<boolean> {
  const s = current;
  if (!s || s.provider !== "oidc") return false;
  const refreshToken = s.refreshToken || (typeof sessionStorage !== "undefined" ? sessionStorage.getItem(REFRESH_KEY) || "" : "");
  if (!refreshToken) return false;
  try {
    const { refreshOidc, oidcSession } = await import("./oidc");
    const config = await fetchAuthConfig();
    if (!config.oidcProvider) return false;
    const tokens = await refreshOidc(refreshToken, config.oidcProvider);
    if (!tokens) return false;
    setSession(oidcSession(tokens));
    return true;
  } catch {
    return false;
  }
}

export type Persona = { key: string; label: string };

/** Named local identities the operator can sign in as (local auth only).
 *
 *  Resolves to an empty list on anything other than a clean 2xx response with
 *  the expected shape — a 404 under `AUTH_MODE=oidc`, an unreachable API, or a
 *  mocked response shaped for a different endpoint all land here, and an empty
 *  list means the sign-in screen falls back to its single default button
 *  rather than rendering a picker with nothing meaningful in it.
 */
export async function fetchPersonas(signal?: AbortSignal): Promise<Persona[]> {
  try {
    const res = await fetch(`${API_URL}/api/v1/auth/personas`, { signal });
    if (!res.ok) return [];
    const body = await res.json();
    const list = body?.data?.personas;
    return Array.isArray(list) ? list.filter((p) => p && typeof p.key === "string" && typeof p.label === "string") : [];
  } catch {
    return [];
  }
}

/** Ask the API for a session. Resolves once a real token is held.
 *
 *  `persona` picks which named local identity to sign in as (see
 *  `fetchPersonas`); omitted, the API issues the default operator identity —
 *  unchanged from before personas existed.
 */
export async function signIn(persona?: string): Promise<Session> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/auth/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(persona ? { persona } : {}),
    });
  } catch {
    throw new Error(
      `Could not reach the VANTOR API at ${API_URL}. Start the backend, or set NEXT_PUBLIC_API_URL to where it is running.`,
    );
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const msg = body?.error?.message || `Sign-in failed (${res.status}).`;
    throw new Error(msg);
  }
  const d = body?.data;
  if (!d?.token) throw new Error("The API did not return a session token.");
  const session: Session = {
    token: d.token,
    name: d.user?.name || "Operator",
    tenant: d.user?.tenant || "",
    roles: Array.isArray(d.user?.roles) ? [...d.user.roles].sort() : [],
    expiresAt: Date.now() + Math.max(0, Number(d.expiresIn) || 0) * 1000,
    persona: typeof d.user?.persona === "string" ? d.user.persona : "",
  };
  if (!session.tenant) {
    // Same rule the Keycloak path enforced: no tenant, no session. The API
    // scopes every row by tenant, so a session without one can only 403.
    throw new Error("The API issued a session with no tenant, so no data can be scoped to it.");
  }
  setSession(session);
  return session;
}

export function logout(): void {
  setSession(null);
}

/** Keep the session from lapsing while a tab is open.
 *
 *  The previous implementation polled the identity provider every 45 seconds
 *  and ended the session the moment a poll failed, which turned an unreachable
 *  IdP — or simply a backgrounded tab — into a forced sign-out. This only acts
 *  when the token is genuinely close to expiring, and a failed renewal leaves
 *  the existing token in place until it actually expires.
 */
export function keepFresh(onExpired: () => void): () => void {
  let dead = false;
  const tick = async () => {
    if (dead) return;
    const s = getSession();
    if (!s) return;
    if (s.expiresAt <= Date.now()) {
      onExpired();
      return;
    }
    if (s.expiresAt - Date.now() > RENEW_BEFORE_MS) return;
    try {
      // Renew as the same persona the session already holds — otherwise a
      // tab left open while acting as "Approver" would silently renew back
      // to the default operator identity partway through, which is exactly
      // the kind of identity-under-your-feet bug personas exist to prevent.
      await signIn(s.persona);
    } catch {
      // Keep the current token; it is still valid. If it does lapse the next
      // tick reports it, and any request that 401s ends the session anyway.
    }
  };
  const id = setInterval(tick, 60_000);
  return () => {
    dead = true;
    clearInterval(id);
  };
}
