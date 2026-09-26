/** Keycloak OIDC — real Authorization Code + PKCE, in-memory tokens only.
 * No stored passwords, no fake sessions, no localStorage tokens. Silent SSO refresh
 * keeps procurement approvals usable on long sessions. Failure => explicit error UI.
 */
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
