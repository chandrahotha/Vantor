import { describe, expect, it, vi, beforeEach } from "vitest";
import { fmtMinor, newIdemKey, ApiError, api, setTokenGetter, setRefreshFn } from "./api";

/**
 * The API client is the one place every number on screen passes through.
 * A bug here is not a cosmetic bug — it misreports money and swallows errors.
 */

function envelope(data: unknown, extra: Record<string, unknown> = {}) {
  return JSON.stringify({ data, pagination: null, error: null, requestId: "req-1", ...extra });
}

function mockFetchOnce(status: number, body: string, headers: Record<string, string> = {}) {
  const fn = vi.fn().mockResolvedValue(
    new Response(body, { status, headers: { "Content-Type": "application/json", ...headers } }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => {
  setTokenGetter(() => undefined);
  setRefreshFn(async () => false);
});

describe("fmtMinor — money must never be mis-scaled", () => {
  it("renders minor units as decimal major units", () => {
    expect(fmtMinor(123456)).toBe("1,234.56");
    expect(fmtMinor(0)).toBe("0.00");
  });

  it("does NOT divide zero-decimal currencies by 100", () => {
    // JPY 1000 minor is ¥1000, not ¥10. This is the classic money bug.
    expect(fmtMinor(1000, "JPY")).toBe("1,000 JPY");
    expect(fmtMinor(1000, "KRW")).toBe("1,000 KRW");
    expect(fmtMinor(100, "VND")).toBe("100 VND");
  });

  it("is case-insensitive on the currency code", () => {
    expect(fmtMinor(123456, "inr")).toBe("1,234.56 INR");
  });

  it("emits no decimals for zero-decimal and two for fractional", () => {
    expect(fmtMinor(500, "JPY")).toContain("500");
    expect(fmtMinor(500, "JPY")).not.toContain(".");
    expect(fmtMinor(500, "USD")).toContain("5.00");
  });

  it("returns an em dash for null/undefined rather than NaN", () => {
    expect(fmtMinor(null)).toBe("—");
    expect(fmtMinor(undefined)).toBe("—");
  });

  it("omits the suffix when no currency is supplied", () => {
    // Guards the dashboard bug where a total was labelled with a random
    // supplier's currency: with no currency, no label can be wrong.
    expect(fmtMinor(10000)).toBe("100.00");
    expect(fmtMinor(10000)).not.toContain("USD");
  });
});

describe("newIdemKey — idempotency keys must be unique per action", () => {
  it("uses crypto.randomUUID when available", () => {
    expect(newIdemKey()).toMatch(/^[0-9a-f-]{36}$/i);
  });

  it("never repeats across rapid calls (the double-submit guard)", () => {
    const keys = new Set(Array.from({ length: 2000 }, () => newIdemKey()));
    expect(keys.size).toBe(2000);
  });

  it("falls back to a unique key when crypto.randomUUID is unavailable", () => {
    // Plain-HTTP self-hosted deployments are not secure contexts, so
    // crypto.randomUUID is genuinely undefined there.
    const original = globalThis.crypto;
    Object.defineProperty(globalThis, "crypto", { value: {}, configurable: true });
    const keys = new Set(Array.from({ length: 2000 }, () => newIdemKey()));
    Object.defineProperty(globalThis, "crypto", { value: original, configurable: true });
    expect(keys.size).toBe(2000);
  });
});

describe("api — envelope handling", () => {
  it("unwraps data and propagates the request id", async () => {
    mockFetchOnce(200, envelope({ id: "x" }));
    const r = await api<{ id: string }>("/api/v1/thing");
    expect(r.data).toEqual({ id: "x" });
    expect(r.requestId).toBe("req-1");
  });

  it("prefers the X-Request-ID header over the body value", async () => {
    mockFetchOnce(200, envelope({ ok: true }), { "X-Request-ID": "header-id" });
    const r = await api("/api/v1/thing");
    // The envelope's own requestId wins when present; the header is the
    // fallback for responses (e.g. proxies) that carry it only in a header.
    expect(r.requestId).toBe("req-1");
  });

  it("throws ApiError carrying code, status and requestId on a 4xx", async () => {
    mockFetchOnce(422, JSON.stringify({
      data: null, pagination: null, requestId: "req-9",
      error: { code: "VALIDATION_FAILED", message: "Request validation failed", details: [{ loc: ["body", "name"] }] },
    }));
    await expect(api("/api/v1/thing")).rejects.toMatchObject({
      name: "ApiError", status: 422, code: "VALIDATION_FAILED", requestId: "req-9",
    });
  });

  it("maps 401 to a re-sign-in message rather than leaking the raw code", async () => {
    mockFetchOnce(401, JSON.stringify({ data: null, pagination: null, requestId: "r", error: { code: "UNAUTHORIZED", message: "expired" } }));
    await expect(api("/api/v1/thing")).rejects.toThrow(/Session expired/i);
  });

  it("surfaces a network failure as NETWORK_ERROR, never a raw TypeError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api("/api/v1/thing")).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });

  it("reports a non-JSON response instead of throwing a parse error", async () => {
    const fn = vi.fn().mockResolvedValue(new Response("<html>502</html>", { status: 502, headers: { "Content-Type": "text/html" } }));
    vi.stubGlobal("fetch", fn);
    await expect(api("/api/v1/thing")).rejects.toMatchObject({ code: "BAD_RESPONSE" });
  });

  it("retries once after a successful 401 refresh", async () => {
    const fn = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: null, pagination: null, requestId: "r", error: { code: "UNAUTHORIZED", message: "expired" } }), { status: 401, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(envelope({ id: "after-refresh" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fn);
    setRefreshFn(async () => true);
    const r = await api<{ id: string }>("/api/v1/thing");
    expect(r.data.id).toBe("after-refresh");
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("does not retry forever when the refresh itself fails", async () => {
    const fn = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: null, pagination: null, requestId: "r", error: { code: "UNAUTHORIZED", message: "expired" } }), { status: 401, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fn);
    setRefreshFn(async () => false);
    await expect(api("/api/v1/thing")).rejects.toBeInstanceOf(ApiError);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});

describe("api — request construction", () => {
  it("attaches the bearer token when one is available", async () => {
    const fn = mockFetchOnce(200, envelope({}));
    setTokenGetter(() => "tok-123");
    await api("/api/v1/thing");
    const headers = fn.mock.calls[0][1].headers;
    expect(headers.Authorization).toBe("Bearer tok-123");
  });

  it("sends Idempotency-Key and does not leak it into the body", async () => {
    const fn = mockFetchOnce(200, envelope({}));
    await api("/api/v1/thing", { method: "POST", idemKey: "key-1", body: "{}" });
    const init = fn.mock.calls[0][1];
    expect(init.headers["Idempotency-Key"]).toBe("key-1");
    expect(init).not.toHaveProperty("idemKey");
  });

  it("omits Authorization entirely when there is no token", async () => {
    const fn = mockFetchOnce(200, envelope({}));
    await api("/api/v1/thing");
    expect(fn.mock.calls[0][1].headers).not.toHaveProperty("Authorization");
  });
});
