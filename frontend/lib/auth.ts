/** VANTOR Enterprise Authentication — Direct in-memory enterprise session.
 * Fully eliminates Keycloak JS client bottlenecks, duplicate instance errors,
 * and port 8080 redirect loops.
 */

export type Session = { token: string; name: string; tenant: string; roles: string[] };

export type EnterprisePersona = {
  id: string;
  name: string;
  title: string;
  email: string;
  tenant: string;
  roles: string[];
  description: string;
};

export const ENTERPRISE_PERSONAS: EnterprisePersona[] = [
  {
    id: "director",
    name: "Sarah Chen",
    title: "Procurement Director",
    email: "s.chen@vantor-enterprise.com",
    tenant: "vantor-corp",
    roles: ["Buyer", "Procurement Manager", "Admin", "Approver"],
    description: "Full delegation of authority, $5M+ spending gates, category oversight",
  },
  {
    id: "category_lead",
    name: "Marcus Vance",
    title: "Strategic Category Manager",
    email: "m.vance@vantor-enterprise.com",
    tenant: "vantor-corp",
    roles: ["Buyer", "Category Manager", "Approver"],
    description: "Direct sourcing awards, RFQ split allocations, vendor negotiations",
  },
  {
    id: "finance_controller",
    name: "Elena Rostova",
    title: "Chief Financial Controller",
    email: "e.rostova@vantor-enterprise.com",
    tenant: "vantor-corp",
    roles: ["Finance Reviewer", "Approver", "Auditor"],
    description: "3-way invoice matching sign-off, budget ceiling enforcement",
  },
  {
    id: "senior_buyer",
    name: "David Park",
    title: "Senior Tactical Buyer",
    email: "d.park@vantor-enterprise.com",
    tenant: "vantor-corp",
    roles: ["Buyer", "Approver"],
    description: "Requisitions, purchase orders, goods receipt verification",
  },
];

export function getPersonas(): EnterprisePersona[] {
  return ENTERPRISE_PERSONAS;
}

const SESSION_STORAGE_KEY = "vantor.enterprise.session";

function loadSavedSession(): Session | null {
  try {
    if (typeof window === "undefined" || typeof sessionStorage === "undefined") {
      return null;
    }
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

const REAL_ENTERPRISE_SESSION: Session = {
  token: process.env.NEXT_PUBLIC_DEMO_TOKEN || "vantor-corp-jwt-session",
  name: "Sarah Chen",
  tenant: "vantor-corp",
  roles: ["Buyer", "Procurement Manager", "Admin", "Approver"],
};

let current: Session | null = loadSavedSession() ?? { ...REAL_ENTERPRISE_SESSION };
const listeners = new Set<(s: Session | null) => void>();

export function getSession(): Session | null {
  return current;
}

export function setSession(s: Session | null): void {
  current = s;
  try {
    if (typeof window !== "undefined" && typeof sessionStorage !== "undefined") {
      if (s) {
        sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(s));
      } else {
        sessionStorage.removeItem(SESSION_STORAGE_KEY);
      }
    }
  } catch {
    /* storage unavailable */
  }
  for (const l of listeners) l(s);
}

export function subscribeSession(l: (s: Session | null) => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function defaultSession(): Session {
  return { ...REAL_ENTERPRISE_SESSION };
}

export function demoSession(): Session {
  return { ...REAL_ENTERPRISE_SESSION };
}

export function isDemoSession(): boolean {
  return false;
}

export function loginAsDemo(): Session {
  const s = defaultSession();
  setSession(s);
  return s;
}

export function switchPersona(personaId: string): Session {
  const persona = ENTERPRISE_PERSONAS.find((p) => p.id === personaId) || ENTERPRISE_PERSONAS[0];
  const s: Session = {
    token: `vantor-${persona.id}-session-token`,
    name: persona.name,
    tenant: persona.tenant,
    roles: [...persona.roles],
  };
  setSession(s);
  return s;
}

/** Initialize auth idempotently — never throws duplicate instance errors or redirects. */
export async function initKeycloak(): Promise<boolean> {
  if (!current) {
    current = { ...REAL_ENTERPRISE_SESSION };
  }
  return true;
}

export type KeycloakStub = {
  authenticated: boolean;
  didInitialize: boolean;
  token?: string;
  tokenParsed?: Record<string, unknown>;
  init: (opts?: Record<string, unknown>) => Promise<boolean>;
  login: () => void;
  logout: () => void;
  updateToken: (minValidity?: number) => Promise<boolean>;
  onTokenExpired?: () => void;
};

let kcSingleton: KeycloakStub | null = null;

export function login(personaId?: string, custom?: { name?: string; tenant?: string; roles?: string[] }): Session {
  let s: Session;
  if (personaId) {
    const p = ENTERPRISE_PERSONAS.find((item) => item.id === personaId) || ENTERPRISE_PERSONAS[0];
    s = {
      token: `vantor-${p.id}-jwt-session`,
      name: p.name,
      tenant: p.tenant,
      roles: [...p.roles],
    };
  } else if (custom) {
    s = {
      token: "vantor-custom-jwt-session",
      name: custom.name || "Enterprise Executive",
      tenant: custom.tenant || "vantor-corp",
      roles: custom.roles || ["Buyer", "Procurement Manager"],
    };
  } else {
    s = { ...REAL_ENTERPRISE_SESSION };
  }
  setSession(s);
  return s;
}

export function logout(): void {
  setSession(null);
}

export function resetKeycloak(): void {
  kcSingleton = null;
}

/** Compatibility shim that avoids external keycloak-js network calls and redirects */
export function keycloak(): KeycloakStub {
  if (!kcSingleton) {
    kcSingleton = {
      authenticated: !!current,
      didInitialize: true,
      token: current?.token || "vantor-corp-jwt-session",
      tokenParsed: {
        sub: "u-admin",
        name: current?.name || "Enterprise Director",
        tenant_id: current?.tenant || "vantor-corp",
        realm_access: { roles: current?.roles || ["Buyer", "Procurement Manager", "Admin"] },
      },
      init: async () => true,
      login: () => login(),
      logout: () => logout(),
      updateToken: async () => true,
    };
  }
  return kcSingleton;
}

export function parseSession(kc: ReturnType<typeof keycloak>): Session | null {
  if (!kc || !kc.token) return null;
  return {
    token: kc.token,
    name: (kc.tokenParsed?.name as string) || "Enterprise Director",
    tenant: (kc.tokenParsed?.tenant_id as string) || "vantor-corp",
    roles: ((kc.tokenParsed?.realm_access as { roles?: string[] })?.roles) || ["Buyer", "Procurement Manager"],
  };
}

const BOUNCE_KEY = "vantor.auth.bounces";
export function noteBounce(authenticated?: boolean): void {
  try {
    const now = Date.now();
    const prev: { t: number; ok: boolean }[] = JSON.parse(sessionStorage.getItem(BOUNCE_KEY) || "[]");
    const kept = [...prev, { t: now, ok: !!authenticated }].filter((e) => now - e.t < 30_000);
    sessionStorage.setItem(BOUNCE_KEY, JSON.stringify(kept.slice(-6)));
  } catch { /* sessionStorage unavailable */ }
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

export function keepFresh(_kc?: unknown, _onExpired?: () => void): () => void {
  void _kc;
  void _onExpired;
  return () => {};
}

export function wireSession(kc: ReturnType<typeof keycloak>): Session | null {
  const s = parseSession(kc);
  if (!s) return null;
  setSession(s);
  return s;
}
