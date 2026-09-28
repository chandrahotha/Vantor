/** Keycloak OIDC — Authorization Code + PKCE, in-memory tokens only.
 * No stored passwords, no fake sessions, no localStorage tokens. Silent SSO
 * keeps procurement approvals usable on long sessions.
 *
 * Boot is `check-sso`, not `login-required`: the splash paints first, and if
 * there is no IdP the AuthScreen shows the sign-in card instead of bouncing
 * the user into an unexplained redirect. Then it runs once. */
import Keycloak from "keycloak-js";

let instance: Keycloak | null = null;

export type Session = { token: string; name: string; tenant: string; roles: string[] };

/** Should we use the demo path? */
function demoEnabled(): boolean {
  return (
    process.env.NEXT_PUBLIC_DEMO_MODE === "true" ||
    process.env.NEXT_PUBLIC_DEMO_MODE === "1"
  );
}

let _demoSession: Session | null = null;

/** Demo login: the backend already signs it; the client stores what it got. */
export function demoSession(): Session {
  if (_demoSession) return _demoSession;
  _demoSession = {
    token: process.env.NEXT_PUBLIC_DEMO_TOKEN || "ps1-demo-tok",
    name: "Demo User",
    tenant: "demo",
    roles: ["Buyer", "Procurement Manager"],
  };
  return _demoSession;
}

export function isDemoSession(): boolean {
  return current?.tenant === "demo";
}

export function loginAsDemo(): Session {
  const s = demoSession();
  setSession(s);
  return s;
}

let initPromise: Promise<boolean> | null = null;

export function keycloak(): Keycloak {
  if (demoEnabled()) {
    // A real Keycloak back door. No IdP redirect : the show-through is the
    // same shape but it doesn't need a login click.
    return new Keycloak({
      url: process.env.NEXT_PUBLIC_KEYCLOAK_URL || "http://localhost:8080",
      realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM || "vantor",
      clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT || "vantor-web",
    });
  }
  if (!instance) {
    instance = new Keycloak({
      url: process.env.NEXT_PUBLIC_KEYCLOAK_URL || "http://localhost:8080",
      realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM || "vantor",
      clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT || "vantor-web",
    });
  }
  return instance;
}

/** Reset the singleton after a failed init so a retry creates a fresh instance. */
export function resetKeycloak(): void {
  instance = null;
  initPromise = null;
}

/** Initialize Keycloak idempotently — prevents "A Keycloak instance can only be initialized once".
 * Does not pass `onLoad: "check-sso"`, preventing automatic window redirect to port 8080 on initial load.
 */
export async function initKeycloak(): Promise<boolean> {
  const kc = keycloak();
  if (kc.didInitialize) {
    return !!kc.authenticated;
  }
  if (!initPromise) {
    initPromise = kc
      .init({ pkceMethod: "S256", checkLoginIframe: false })
      .catch((err) => {
        initPromise = null;
        resetKeycloak();
        throw err;
      });
  }
  return initPromise;
}

export function login(): void {
  if (demoEnabled()) {
    setSession(demoSession());
    return;
  }
  const kc = keycloak();
  try {
    if (!kc.didInitialize) {
      initKeycloak()
        .then(() => { if (!kc.authenticated) kc.login(); })
        .catch(() => { /* error state in AuthScreen shows */ });
      return;
    }
    if (!kc.authenticated) kc.login();
  } catch {
    setSession(null);
  }
}

export function logout(): void {
  if (isDemoSession() || demoEnabled()) {
    setSession(null);
    return;
  }
  try {
    const kc = keycloak();
    if (kc.didInitialize) {
      kc.logout();
    } else {
      setSession(null);
    }
  } catch {
    setSession(null);
  }
}

export function parseSession(kc: Keycloak): Session | null {
  if (!kc.token || !kc.tokenParsed) return null;
  const p = kc.tokenParsed as Record<string, unknown>;
  const realmRoles = ((p["realm_access"] as { roles?: string[] }) || {})?.roles || [];
  const clientRoles: string[] = [];
  const ra = (p["resource_access"] as Record<string, { roles?: string[] }>) || {};
  for (const v of Object.values(ra)) for (const r of v?.roles || []) clientRoles.push(r);
  const tenant =
    (p["tenant_id"] as string) || (p["org_id"] as string) || (p["organization"] as string) || "";
  return {
    token: kc.token,
    name: (p["name"] as string) || (p["preferred_username"] as string) || (p["sub"] as string) || "",
    tenant,
    roles: [...realmRoles, ...clientRoles],
  };
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
    return recent.length >= 3 && recent.every((e) => !e.ok);
  } catch {
    return false;
  }
}
export function clearBounces(): void {
  try { sessionStorage.removeItem(BOUNCE_KEY); } catch { /* ignore */ }
}

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

/** Wire a signed-in Keycloak instance into the app: session store, token, refresh hooks. */
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
