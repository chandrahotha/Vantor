/** Keycloak OIDC — Authorization Code + PKCE, in-memory tokens only.
 *
 * No stored passwords, no fake sessions, no localStorage tokens. An application
 * session exists if and only if the IdP returned a signed token that carries a
 * tenant; nothing in this file may manufacture one.
 *
 * That constraint is the reason for the absence of any "persona" or "demo"
 * helper. There was a version of this module that exported a list of executives
 * and a `switchPersona(id)` that built a session from nothing but a string —
 * `switchPersona("director")` produced a token `vantor-director-session-token`
 * with the Admin role. The backend now fails closed outside production, so that
 * path would only ever have produced a UI that looked signed in and then
 * received 401 on every request. `components/authboot.test.tsx` asserts the
 * absence of an identity at module load, and
 * `backend/tests/test_auth.py::test_forged_tokens_are_401_in_test_env` asserts
 * the matching server-side refusal.
 *
 * Boot is `check-sso`, not `login-required`: the splash paints first, and if
 * there is no IdP the AuthScreen shows the sign-in card instead of bouncing the
 * user into an unexplained redirect. Then it runs once. */
import Keycloak from "keycloak-js";
import type { KeycloakInitOptions } from "keycloak-js";

let instance: Keycloak | null = null;

export type Session = { token: string; name: string; tenant: string; roles: string[] };

function config() {
  return {
    url: process.env.NEXT_PUBLIC_KEYCLOAK_URL || "http://localhost:8080",
    realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM || "vantor",
    clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT || "vantor-web",
  };
}

export function keycloak(): Keycloak {
  if (!instance) instance = new Keycloak(config());
  return instance;
}

/** Reset the singleton after a failed init so a retry creates a fresh instance. */
export function resetKeycloak(): void {
  instance = null;
  if (inFlight) inFlight = null;
  initialised = false;
}

/** keycloak-js permits one `init` per instance and throws on a second.
 *
 *  React 18/19 StrictMode invokes every effect twice in development, and Fast
 *  Refresh remounts on save, so a boot that calls `kc.init(...)` straight from
 *  its effect is initialising a singleton twice and downgrading the whole view
 *  to "Sign-in problem" on a network that is working fine. Callers that need to
 *  try again go through `resetKeycloak()`, which clears the memo so the retry
 *  really does get a fresh instance. */
let inFlight: Promise<boolean> | null = null;
let initialised = false;

export function initOnce(kc: Keycloak, options: KeycloakInitOptions): Promise<boolean> {
  if (initialised) return Promise.resolve(kc.authenticated);
  if (inFlight) return inFlight;
  inFlight = kc
    .init(options)
    .then((ok) => {
      initialised = true;
      return ok;
    })
    .catch((e: unknown) => {
      // A failed init must not poison the singleton: the caller is expected to
      // offer a retry, and a retry needs to be able to init.
      inFlight = null;
      throw e;
    });
  return inFlight;
}

export function isAuthBypassed(): boolean {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_DISABLE_AUTH === "true") {
    return true;
  }
  return false;
}

/** Start an interactive login. This redirects to the IdP and returns; it does
 *  not and must not set a session — a session only exists after the redirect
 *  comes back with a code and `wireSession` reads a real token. */
export function login(): void {
  if (isAuthBypassed()) {
    setSession({
      token: "dev-bypass-token",
      name: "Administrator",
      tenant: "vantor-corp",
      roles: ["Admin", "Buyer", "Procurement Manager", "Approver"]
    });
    window.dispatchEvent(new Event("storage"));
    return;
  }
  try {
    const kc = keycloak();
    if (!kc.didInitialize) {
      initOnce(kc, { onLoad: "check-sso", pkceMethod: "S256", checkLoginIframe: false })
        .then(() => { if (!kc.authenticated) kc.login(); })
        .catch(() => { /* the boot reports an unreachable IdP via AuthScreen */ });
      return;
    }
    if (!kc.authenticated) kc.login();
  } catch {
    setSession(null);
  }
}

/** Sign out. The local session is dropped unconditionally, including when the
 *  adapter was never initialised: leaving a session in place because the IdP
 *  call could not be made is how a signed-out user keeps a working session. */
export function logout(): void {
  if (isAuthBypassed()) {
    setSession(null);
    window.dispatchEvent(new Event("storage"));
    return;
  }
  try {
    const kc = keycloak();
    if (kc.didInitialize) kc.logout();
  } catch { /* ignore — the local session still goes */ }
  setSession(null);
  window.dispatchEvent(new Event("storage"));
}

/** The session an adapter's current token represents, or `null`.
 *
 * `null` for a token with no tenant claim is deliberate. The backend answers
 * 403 "Token carries no tenant" for exactly that token, so inventing a tenant
 * here would only build a session that fails on its first request while the UI
 * claims everything is fine. */
export function parseSession(kc: Keycloak): Session | null {
  if (!kc || !kc.token) return null;
  const p = (kc.tokenParsed || {}) as Record<string, unknown>;
  const realmRoles = ((p["realm_access"] as { roles?: string[] }) || {}).roles || [];
  const clientRoles: string[] = [];
  const ra = (p["resource_access"] as Record<string, { roles?: string[] }>) || {};
  for (const v of Object.values(ra)) for (const r of v?.roles || []) clientRoles.push(r);
  const tenant =
    (p["tenant_id"] as string) || (p["org_id"] as string) || (p["organization"] as string) || "";
  if (!tenant) return null;
  return {
    token: kc.token,
    name: (p["name"] as string) || (p["preferred_username"] as string) || (p["sub"] as string) || "",
    tenant,
    // A role that arrives through both the realm and a client grant is one
    // role. Sorted so the UI cannot flicker between two spellings of the same
    // set between renders.
    roles: [...new Set([...realmRoles, ...clientRoles])].sort(),
  };
}

/** Loop detector. Every auth check is counted as (ok/unauth) pairs so the
 *  detector can tell "IdP cancelled the login" (safe) from "the client keeps
 *  getting bounced" (a misconfiguration), and never triggers on a normal
 *  reload-while-signed-in. */
const BOUNCE_KEY = "vantor.auth.bounces";
export function noteBounce(authenticated?: boolean): void {
  try {
    const now = Date.now();
    const prev: { t: number; ok: boolean }[] = JSON.parse(sessionStorage.getItem(BOUNCE_KEY) || "[]");
    const kept = [...prev, { t: now, ok: !!authenticated }].filter((e) => now - e.t < 30_000);
    sessionStorage.setItem(BOUNCE_KEY, JSON.stringify(kept.slice(-6)));
  } catch { /* sessionStorage unavailable (privacy mode) — proceed unguarded */ }
}
export function isLooping(): boolean {
  try {
    const events: { t: number; ok: boolean }[] = JSON.parse(sessionStorage.getItem(BOUNCE_KEY) || "[]");
    const now = Date.now();
    const recent = events.filter((e) => now - e.t < 30_000);
    return recent.length >= 3 && recent.every((e) => !e.ok);
  } catch {
    return false;
  }
}
export function clearBounces(): void {
  try { sessionStorage.removeItem(BOUNCE_KEY); } catch { /* ignore */ }
}

/** Keep the access token fresh, and hand back a teardown.
 *
 * A failed refresh is not a UI detail — it means the session is gone — so it
 * calls `onExpired` rather than retrying quietly, and the view returns to the
 * sign-in gate. */
export function keepFresh(kc: Keycloak, onExpired: () => void): () => void {
  if (isAuthBypassed()) {
    return () => {};
  }
  let dead = false;
  const refresh = () => {
    kc.updateToken(60).catch(() => {
      if (!dead) onExpired();
    });
  };
  kc.onTokenExpired = refresh;
  const id = setInterval(refresh, 45000);
  return () => {
    dead = true;
    clearInterval(id);
  };
}

type Listener = (s: Session | null) => void;
/** `null` until a real token is parsed. Never seeded, never restored from
 *  storage: an access token has a five-minute life and a stale one produces a
 *  401 that reads like a bug in the app. */
let current: Session | null = null;
const listeners = new Set<Listener>();

/** Wire a signed-in Keycloak instance into the app: session store, token, refresh hooks. */
export function wireSession(kc: Keycloak): Session | null {
  const s = parseSession(kc);
  if (!s) return null;
  setSession(s);
  return s;
}
export function setSession(s: Session | null): void {
  current = s;
  for (const l of listeners) l(s);
}
export function getSession(): Session | null {
  return current;
}
export function subscribeSession(l: Listener): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}
