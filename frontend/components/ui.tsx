"use client";
/** Shared UI primitives.
 *
 *  These exist because the same four things were hand-written across the app:
 *  a cursor pager (4×), a stat card (8×), a raw `<table className="grid">` (9×)
 *  and a Keycloak boot block (5×, with divergent copy). Centralising them is what
 *  makes adding write paths safe — a new form inherits the loading, error and
 *  empty-state handling instead of reinventing it.
 */
import Image from "next/image";
import { useCallback, useEffect, useRef, useState } from "react";
import { clearBounces, isLooping, keycloak, login, noteBounce, parseSession, keepFresh, setSession } from "../lib/auth";
import { setTokenGetter, setRefreshFn } from "../lib/api";

export function Badge({ tone, children }: { tone?: "ok" | "warn" | "bad" | "info"; children: React.ReactNode }) {
  return <span className={`badge${tone ? ` ${tone}` : ""}`}>{children}</span>;
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty" role="status">
      <div style={{ fontWeight: 700, color: "#0f172a" }}>{title}</div>
      {hint ? <div style={{ marginTop: 6 }}>{hint}</div> : null}
    </div>
  );
}

export function ErrorBox({ message, requestId }: { message: string; requestId?: string }) {
  return (
    <div className="error" role="alert">
      <div>{message}</div>
      {requestId ? <div className="mono" style={{ fontSize: 12, marginTop: 4 }}>request {requestId}</div> : null}
    </div>
  );
}

export function Skeleton({ rows = 3, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-busy="true" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div className="skel" key={i} aria-hidden="true" />
      ))}
    </div>
  );
}

export function StatCard({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" | "warn" }) {
  return (
    <div className="card">
      <div className="k">{label}</div>
      <div className={`v mono${tone ? ` ${tone}` : ""}`}>{value}</div>
    </div>
  );
}

/** Server-side cursor pager. Keeps its own back-stack so "Prev" is correct
 *  after an arbitrary number of Next clicks. */
export function Pager({ stack, onPrev, hasMore, onNext, busy }: {
  stack: string[];
  onPrev: () => void;
  hasMore: boolean;
  onNext: () => void;
  busy?: boolean;
}) {
  return (
    <div className="pager">
      <button className="ghost" disabled={busy || stack.length === 0} onClick={onPrev}>← Prev</button>
      <span className="mono" style={{ fontSize: 12 }}>page {stack.length + 1}</span>
      <button className="ghost" disabled={busy || !hasMore} onClick={onNext}>Next →</button>
    </div>
  );
}

export type Column<T> = {
  key: string;
  header: string;
  /** Money columns must be rendered via `fmtMinor` with a currency, never raw. */
  numeric?: boolean;
  sortable?: boolean;
  render: (row: T) => React.ReactNode;
};

/** Accessible data grid: caption, column scope, and `aria-sort` on the active
 *  sort column so the sort state is announced rather than implied by a glyph. */
export function DataTable<T>({ caption, rows, rowKey, columns, sort, order, onSort, empty }: {
  caption: string;
  rows: T[];
  rowKey: (row: T) => string;
  columns: Column<T>[];
  sort?: string;
  order?: "asc" | "desc";
  onSort?: (key: string) => void;
  empty: React.ReactNode;
}) {
  if (rows.length === 0) return <>{empty}</>;
  return (
    <div className="gridwrap">
      <table className="grid">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => {
              const active = sort === c.key;
              const ariaSort = active ? (order === "asc" ? "ascending" : "descending") : c.sortable ? "none" : undefined;
              return (
                <th key={c.key} scope="col" aria-sort={ariaSort} className={c.numeric ? "num" : undefined}>
                  {c.sortable && onSort ? (
                    <button onClick={() => onSort(c.key)}>
                      {c.header} {active ? (order === "asc" ? "↑" : "↓") : ""}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)}>
              {columns.map((c) => (
                <td key={c.key} className={c.numeric ? "num" : undefined}>{c.render(r)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type BootState = "loading" | "signin" | "error" | "ok";

/** Single Keycloak entry point for every page.
 *
 *  Replaces five hand-copied init blocks that had drifted apart in their error
 *  copy and in whether they set the API token hooks. Returns an unsubscribe for
 *  `useEffect`, and — unlike the originals — does not call `kc.init()` twice
 *  under `reactStrictMode`, because the effect owns a cancellation flag.
 *
 *  Redirect discipline: `login-required` bounces instantly to the IdP. To keep
 *  that invisible bounce from looking like a crash, the caller renders
 *  `<AuthScreen state="loading">` as a branded splash. Rapid repeated bounces
 *  (misconfigured IdP/realm/client) are detected and downgraded to an explicit
 *  "sign-in loop" error instead of an infinite redirect.
 */
export function useBoot(load: () => Promise<void>) {
  const [state, setState] = useState<BootState>("loading");
  const [error, setError] = useState("");
  const loadRef = useRef(load);

  // Keep the latest callback without re-running the effect. The assignment is in
  // an effect (not render) so the lint rule for ref writes is satisfied, and the
  // ref is only ever *read* inside the async callback below.
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let disposed = false;
    let stop: () => void = () => {};

    (async () => {
      const kc = keycloak();
      try {
        // check-sso: never auto-redirect. When the IdP has a session we proceed
        // silently; when it does not, AuthScreen shows the sign-in card.
        await kc.init({ onLoad: "check-sso", pkceMethod: "S256", checkLoginIframe: false });
        if (disposed) return;
        noteBounce(!!kc.authenticated);
        if (!kc.authenticated) {
          if (isLooping()) {
            setError(
              "Sign-in is looping — the identity provider or client is misconfigured. Check NEXT_PUBLIC_KEYCLOAK_URL, the realm, and the redirect URI.",
            );
            setState("error");
          } else {
            setState("signin");
          }
          return;
        }
        clearBounces();
        const s = parseSession(kc);
        if (!s?.tenant) {
          setError("Your session carries no tenant, so access is refused. Contact your administrator.");
          setState("error");
          return;
        }
        setSession(s);
        setTokenGetter(() => keycloak().token);
        setRefreshFn(async () => {
          try {
            const fresh = await keycloak().updateToken(60);
            if (fresh) {
              const ns = parseSession(keycloak());
              if (ns) setSession(ns);
            }
            return true;
          } catch {
            return false;
          }
        });
        stop = keepFresh(kc, () => setError("Session expired — please sign in again."));
        if (disposed) return;
        await loadRef.current();
        if (!disposed) setState("ok");
        document.documentElement.dataset.booted = "true";
      } catch (e: unknown) {
        if (disposed) return;
        const msg = e instanceof Error ? e.message : "";
        if (disposed || msg.toLowerCase().includes("active")) {
          // "check-sso" on first paint means no session — show the card.
          setState("signin");
          return;
        }
        setError(
          msg
            ? `Identity provider unreachable — check NEXT_PUBLIC_KEYCLOAK_URL. (${msg})`
            : "Sign-in failed.",
        );
        setState("error");
      }
    })();

    return () => {
      disposed = true;
      stop();
    };
  }, []);

  const reload = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      await loadRef.current();
      setState("ok");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Load failed");
      setState("error");
    }
  }, []);

  return { state, error, reload };
}

/** Full-viewport states that answer "where did the page go?" Before this
 *  existed, an unauthenticated load flashed a blank frame and vanished into the
 *  IdP redirect, which read as a bug. */
export function AuthScreen({ state, error }: { state: BootState; error?: string }) {
  if (state === "ok") return null;
  if (state === "loading") {
    return (
      <div className="authscreen" role="status" aria-live="polite">
        <Image src="/icons/icon-192.png" alt="VANTOR" width={72} height={72} className="authscreen-mark-img" />
        <p className="authscreen-title">Opening VANTOR…</p>
        {error ? <p className="authscreen-sub">{error}</p> : null}
      </div>
    );
  }
  return (
    <div className="authscreen" role={state === "error" ? "alert" : "status"}>
      <Image src="/icons/icon-192.png" alt="VANTOR" width={72} height={72} className="authscreen-mark-img" />
      <p className="authscreen-title">
        {state === "signin" ? "Sign in to VANTOR" : "Could not start VANTOR"}
      </p>
      {error ? <p className="authscreen-sub">{error}</p> : null}
      {state === "signin" || state === "error" ? (
        <button className="authscreen-cta" onClick={() => login()}>
          Continue with Vantor ID
        </button>
      ) : null}
    </div>
  );
}

/** Live-region wrapper so async results are announced to screen readers
 *  instead of appearing silently. */
export function LiveRegion({ children }: { children: React.ReactNode }) {
  return (
    <div aria-live="polite" aria-atomic="true">
      {children}
    </div>
  );
}
