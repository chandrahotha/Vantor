/** Vantor API client — envelope-aware, request-ID propagated, token-in-memory only.
 * No localStorage tokens (memory + Keycloak silent refresh). Every response is the
 * backend envelope {data,pagination,error,requestId}; HTTP errors surface the
 * envelope error code, never a raw stack. Empty data renders empty states upstream.
 */
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { getSession } from "./auth";

export type Envelope<T> = {
  data: T | null;
  pagination: { limit: number; nextCursor: string; hasMore: boolean; [k: string]: unknown } | null;
  error: { code: string; message: string; details: unknown } | null;
  requestId: string;
};

export class ApiError extends Error {
  code: string;
  status: number;
  requestId: string;
  constructor(status: number, code: string, message: string, requestId: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

/** The bearer to send, or `undefined` when there is no verified identity.
 *
 *  There is deliberately no fallback. This defaulted to the literal
 *  "vantor-corp-jwt-session" — a string that is not a signed token at all — so
 *  if the boot ever failed to register a getter, every request went out
 *  carrying a fabricated credential instead of none. The backend accepted it as
 *  a full Admin in non-production (removed) and rejects it with 401 now, so the
 *  failure mode has moved from "silently privileged" to "every call 401s",
 *  which is at least visible. No unauthenticated request is ever sent. */
let tokenGetter: () => string | undefined = () => getSession()?.token;
export function setTokenGetter(fn: () => string | undefined) {
  tokenGetter = fn;
}

let refreshFn: () => Promise<boolean> = async () => false;
export function setRefreshFn(fn: () => Promise<boolean>) {
  refreshFn = fn;
}

/** Called when a 401 survives one real refresh attempt, i.e. the token the app
 *  holds is not one the backend will accept. The auth layer uses this to end the
 *  session; without it a dead token leaves the user staring at a page whose
 *  every panel errors. Deliberately not a fallback to any local identity — the
 *  only outcome is "signed out, sign in again". */
let unauthorizedFn: (() => void) | null = null;
/** Register what should happen when the backend rejects the token *after* a
 *  real refresh attempt. `null` unregisters, which the boot's cleanup does —
 *  otherwise a page that unmounts would leave its handler installed and the next
 *  page's 401 would drive a closure over dead state. */
export function setUnauthorizedHandler(fn: (() => void) | null) {
  // Kept for signature compatibility if needed, but we now use events.
  unauthorizedFn = fn;
}

/** Idempotency key for writes that must not double-execute.
 *  `crypto.randomUUID` is a secure-context API, so plain-HTTP self-hosted
 *  deployments fall back to a counter+clock pair. Module scope keeps it out of
 *  render, which is what `react-hooks/purity` guards against. */
let fallbackSeq = 0;
export function newIdemKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  fallbackSeq += 1;
  return `idem-${Date.now().toString(36)}-${fallbackSeq.toString(36)}`;
}

export type ApiOptions = Omit<RequestInit, "headers"> & {
  headers?: Record<string, string>;
  /** Pass an explicit key for operations that must not double-execute (resolve, approvals). */
  idemKey?: string;
};

/** Human-readable copy for a failed request. Never a bare status number. */
export function friendly(status: number, code: string, message: string): string {
  if (status === 401) return "Session expired — please sign in again.";
  if (status === 403) return `Not permitted (${code}). Your role lacks access.`;
  if (status === 409) return `Conflict (${code}): ${message}`;
  if (status === 422) return message;
  if (status === 429) return "Too many requests — please wait a minute and retry.";
  return message || `Request failed (${status})`;
}

export async function api<T>(path: string, init?: ApiOptions, retried = false): Promise<{ data: T; pagination: Envelope<T>["pagination"]; requestId: string }> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init?.headers || {}) };
  const token = tokenGetter();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (init?.idemKey) headers["Idempotency-Key"] = init.idemKey;
  let res: Response;
  try {
    const { idemKey: _drop, ...rest } = init || {};
    void _drop;
    res = await fetch(`${API_URL}${path}`, { ...rest, headers });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "API unreachable — is the backend running?", "");
  }
  if (res.status === 401 && !retried) {
    try {
      if (await refreshFn()) return api<T>(path, init, true);
    } catch { /* fall through to friendly 401 */ }
  }
  // A 401 that survived the refresh attempt means the identity is gone, not
  // stale. Report it once, after the body has been read below, so the session
  // ends in the same tick the caller learns the request failed.
  const unauthorized = res.status === 401;
  const rid = res.headers.get("X-Request-ID") || "";
  let body: Envelope<T>;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.status, "BAD_RESPONSE", `Non-JSON response (${res.status})`, rid);
  }
  if (!res.ok || body.error) {
    const code = body.error?.code || "REQUEST_FAILED";
    if (unauthorized) {
      unauthorizedFn?.();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("vantor:unauthorized"));
      }
    }
    throw new ApiError(res.status, code, friendly(res.status, code, body.error?.message || ""), body.requestId || rid);
  }
  return { data: body.data as T, pagination: body.pagination, requestId: body.requestId || rid };
}

// Zero-decimal currencies must NOT be divided by 100 (JPY, KRW, VND, ...).
const ZERO_DECIMAL = new Set(["JPY", "KRW", "VND", "CLP", "ISK", "UGX", "TZS"]);

export function fmtMinor(minor: number | null | undefined, currency?: string): string {
  if (minor === null || minor === undefined) return "—";
  const ccy = (currency || "").toUpperCase();
  const divisor = ccy && ZERO_DECIMAL.has(ccy) ? 1 : 100;
  const frac = divisor === 1 ? 0 : 2;
  try {
    const num = (minor / divisor).toLocaleString("en-IN", { minimumFractionDigits: frac, maximumFractionDigits: frac });
    return ccy ? `${num} ${ccy}` : num;
  } catch {
    return `${minor}${ccy ? ` ${ccy}` : ""}`;
  }
}
