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

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
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
};

type Listener = (s: Session | null) => void;

let current: Session | null = null;
const listeners = new Set<Listener>();

export function getSession(): Session | null {
  return current;
}

export function setSession(s: Session | null): void {
  current = s;
  try {
    if (s) localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
    else localStorage.removeItem(STORAGE_KEY);
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
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    if (!isLive(parsed)) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    current = parsed;
    for (const l of listeners) l(parsed);
    return parsed;
  } catch {
    return null;
  }
}

export type AuthConfig = { local: boolean; oidc: boolean; productName: string };

export async function fetchAuthConfig(signal?: AbortSignal): Promise<AuthConfig> {
  const res = await fetch(`${API_URL}/api/v1/auth/config`, { signal });
  if (!res.ok) throw new Error(`The API answered ${res.status} when asked how to sign in.`);
  const body = await res.json();
  return body.data as AuthConfig;
}

/** Ask the API for a session. Resolves once a real token is held. */
export async function signIn(): Promise<Session> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/auth/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
      await signIn();
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
