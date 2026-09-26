/** Vantor API client — envelope-aware, request-ID propagated, token-in-memory only.
 * No localStorage tokens (memory + Keycloak silent refresh). Every response is the
 * backend envelope {data,pagination,error,requestId}; HTTP errors surface the
 * envelope error code, never a raw stack. Empty data renders empty states upstream.
 */
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

let tokenGetter: () => string | undefined = () => undefined;
export function setTokenGetter(fn: () => string | undefined) {
  tokenGetter = fn;
}

let refreshFn: () => Promise<boolean> = async () => false;
export function setRefreshFn(fn: () => Promise<boolean>) {
  refreshFn = fn;
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

function friendly(status: number, code: string, message: string): string {
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
  const rid = res.headers.get("X-Request-ID") || "";
  let body: Envelope<T>;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.status, "BAD_RESPONSE", `Non-JSON response (${res.status})`, rid);
  }
  if (!res.ok || body.error) {
    const code = body.error?.code || "REQUEST_FAILED";
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
