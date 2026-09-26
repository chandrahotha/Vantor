/** Keycloak OIDC — Authorization Code + PKCE, in-memory tokens only.
 * No stored passwords, no fake sessions, no localStorage tokens. Silent SSO
 * refresh keeps procurement approvals usable on long sessions.
 *
 * Boot is `check-sso`, not `login-required`: the splash paints first, and when
 * the IdP has no session we show a sign-in card instead of bouncing the user
 * into an unexplained redirect. That is also what kills the "page appears and
 * immediately disappears" class of bug. */
import Keycloak from "keycloak-js";

let instance: Keycloak | null = null;

export function keycloak(): Keycloak {
  if (!instance) {
    instance = new Keycloak({
      url: process.env.NEXT_PUBLIC_KEYCLOAK_URL || "http://localhost:8080",
      realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM || "vantor",
      clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT || "vantor-web",
    });
  }
  return instance;
}

export function login(): void {
  const kc = keycloak();
  try {
    // login() before init() throws in keycloak 26 — bootstrap, then redirect.
    if (!kc.didInitialize) {
      kc.init({ onLoad: "check-sso", pkceMethod: "S256", checkLoginIframe: false })
        .then(() => { if (!kc.authenticated) kc.login(); })
        .catch(() => { /* the error state in AuthScreen shows */ });
      return;
    }
    if (!kc.authenticated) kc.login();
  } catch {
    // Adapter itself is unavailable in this bundle. The AuthScreen error state
    // is the honest answer; never crash a click handler.
    setSession(null);
  }
}

export function logout(): void {
  try {
    const kc = keycloak();
    if (kc.didInitialize) kc.logout();
  } catch { /* ignore */ }
}

/** Loop detector. Every auth check is counted as (ok/unauth) pairs so the
 *  detector can tell "IdP cancelled the login" (safe) from "the client keeps
 *  getting bounced" (a misconfiguration), and never triggers on a normal
 *  reload-while-signed-in. */
const BOUNCE_KEY = "vantor.auth.bounces";
export function noteBounce(authenticated: boolean): void {
  try {
    const now = Date.now();
    const prev: { t: number; ok: boolean }[] = JSON.parse(sessionStorage.getItem(BOUNCE_KEY) || "[]");
    const kept = [...prev, { t: now, ok: authenticated }].filter((e) => now - e.t < 30_000);
    sessionStorage.setItem(BOUNCE_KEY, JSON.stringify(kept.slice(-6)));
  } catch { /* sessionStorage unavailable (privacy mode) — proceed unguarded */ }
}
export function isLooping(): boolean {
  try {
    const events: { t: number; ok: boolean }[] = JSON.parse(sessionStorage.getItem(BOUNCE_KEY) || "[]");
    const now = Date.now();
    const recent = events.filter((e) => now - e.t < 30_000);
    // Only a loop if we keep failing AND have not had a success recently.
    return recent.length >= 3 && recent.every((e) => !e.ok);
  } catch {
    return false;
  }
}
export function clearBounces(): void {
  try { sessionStorage.removeItem(BOUNCE_KEY); } catch { /* ignore */ }
}

export type Session = { token: string; name: string; tenant: string; roles: string[] };

export function parseSession(kc: Keycloak): Session | null {
  if (!kc.token || !kc.tokenParsed) return null;
  const p = kc.tokenParsed as Record<string, unknown>;
  const realmRoles = ((p["realm_access"] as { roles?: string[] }) || {}).roles || [];
  const clientRoles: string[] = [];
  const ra = (p["resource_access"] as Record<string, { roles?: string[] }>) || {};
  for (const v of Object.values(ra)) for (const r of v.roles || []) clientRoles.push(r);
  const tenant =
    (p["tenant_id"] as string) || (p["org_id"] as string) || (p["organization"] as string) || "";
  return {
    token: kc.token,
    name: (p["name"] as string) || (p["preferred_username"] as string) || (p["sub"] as string) || "",
    tenant,
    roles: [...realmRoles, ...clientRoles],
  };
}

/** Keeps long procurement sessions alive; returns a cleanup for useEffect.
 * Never force-redirects: on refresh failure the caller shows re-sign-in UI
 * (redirects would wipe copilot drafts, calc inputs and search state). */
export function keepFresh(kc: Keycloak, onExpired: () => void): () => void {
  let dead = false;
  kc.onTokenExpired = () => {
    kc.updateToken(60).catch(() => {
      if (!dead) onExpired();
    });
  };
  const id = setInterval(() => {
    kc.updateToken(60).catch(() => {
      if (!dead) onExpired();
    });
  }, 45000);
  return () => {
    dead = true;
    clearInterval(id);
  };
}

type Listener = (s: Session | null) => void;
let current: Session | null = null;
const listeners = new Set<Listener>();

/** Wire a signed-in Keycloak instance into the app: session store, token + refresh hooks. */
export function wireSession(kc: Keycloak): Session | null {
  const s = parseSession(kc);
  if (!s) return null;
  setSession(s);
  return s;
}
export function setSession(s: Session | null) {
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
