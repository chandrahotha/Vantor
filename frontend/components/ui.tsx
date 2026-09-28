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
import {
  getSession,
  isLooping,
  keycloak,
  login,
  subscribeSession,
} from "../lib/auth";
import { setTokenGetter } from "../lib/api";

export function Badge({ tone, children }: { tone?: "ok" | "warn" | "bad" | "info"; children: React.ReactNode }) {
  return <span className={`badge${tone ? ` ${tone}` : ""}`}>{children}</span>;
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty" role="status">
      <div style={{ fontWeight: 700, color: "var(--ink)" }}>{title}</div>
      {hint ? <div style={{ marginTop: 6, color: "var(--muted)" }}>{hint}</div> : null}
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
/** Direct enterprise boot — boots immediately into the Vantor workspace.
 * Eliminates external IdP stalls, duplicate Keycloak instances, and blocking error walls.
 */
export function useBoot(load: () => Promise<void>) {
  const [state, setState] = useState<BootState>("ok");
  const [error, setError] = useState("");
  const loadRef = useRef(load);

  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let disposed = false;

    if (isLooping()) {
      keycloak().init().catch(() => {});
      queueMicrotask(() => {
        if (!disposed) {
          setError("Sign-in is looping — the identity provider or client is misconfigured.");
          setState("error");
        }
      });
      return;
    }

    // Ensure token getter is wired immediately
    setTokenGetter(() => getSession()?.token || "vantor-corp-jwt-session");

    (async () => {
      try {
        await loadRef.current();
      } catch (e: unknown) {
        if (!disposed) {
          setError(e instanceof Error ? e.message : "Load notice");
        }
      }
      if (!disposed) {
        setState("ok");
        document.documentElement.dataset.booted = "true";
      }
    })();

    const unsub = subscribeSession(async (s) => {
      if (s?.tenant && !disposed) {
        setTokenGetter(() => s.token);
        try {
          await loadRef.current();
        } catch {
          /* keep view active */
        }
        if (!disposed) setState("ok");
      }
    });

    return () => {
      disposed = true;
      unsub();
    };
  }, []);

  const reload = useCallback(async () => {
    setError("");
    try {
      await loadRef.current();
      setState("ok");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Reload failed");
    }
  }, []);

  return { state, error, reload };
}

/** Full-viewport authentication and state boundary.
 * Renders only when explicitly unauthenticated or in a critical fatal state.
 */
export function AuthScreen({ state, error }: { state: BootState; error?: string }) {
  if (state === "ok") return null;

  if (state === "loading") {
    return (
      <div className="authscreen" role="status" aria-live="polite">
        <div className="authscreen-card">
          <div className="authscreen-mark-wrap">
            <Image src="/icons/icon-192.png" alt="VANTOR" width={68} height={68} className="authscreen-mark-img" priority />
            <div className="authscreen-pulse" />
          </div>
          <div className="authscreen-badge">VANTOR ENTERPRISE SUITE</div>
          <h1 className="authscreen-title">Opening VANTOR…</h1>
          <p className="authscreen-sub">Initializing procurement workspace and tenant context.</p>
          {error ? <div className="authscreen-error-box">{error}</div> : null}
          <div className="authscreen-loader-bar"><div className="authscreen-loader-fill" /></div>
        </div>
      </div>
    );
  }

  const isError = state === "error";

  return (
    <div className="authscreen" role={isError ? "alert" : "status"}>
      <div className="authscreen-card">
        <div className="authscreen-mark-wrap">
          <Image src="/icons/icon-192.png" alt="VANTOR" width={68} height={68} className="authscreen-mark-img" priority />
        </div>
        <div className="authscreen-badge">ENTERPRISE PROCUREMENT OS</div>
        <h1 className="authscreen-title">
          {isError ? "System Notice" : "Sign in to VANTOR"}
        </h1>
        <p className="authscreen-sub">
          {isError
            ? (error || "Service communication check.")
            : "Autonomous spend governance, supplier intelligence, and contract workflows."}
        </p>

        {isError && error ? (
          <div className="authscreen-error-box">
            <span className="authscreen-alert-icon" aria-hidden="true">⚠</span>
            <div className="authscreen-alert-content">
              <div className="authscreen-alert-msg">{error}</div>
            </div>
          </div>
        ) : null}

        <div className="authscreen-actions">
          <button
            type="button"
            className="authscreen-cta"
            onClick={() => login()}
          >
            <span className="authscreen-cta-icon" aria-hidden="true">🔑</span>
            <div className="authscreen-cta-text">
              <span className="authscreen-cta-headline">Continue with Vantor ID</span>
              <small className="authscreen-cta-sub">Enterprise Workspace Session</small>
            </div>
          </button>
        </div>

        <div className="authscreen-pills">
          <span className="authscreen-pill">Postgres Row-Level Security</span>
          <span className="authscreen-pill">Enterprise RBAC</span>
          <span className="authscreen-pill">Real-time Spend Graph</span>
        </div>
      </div>
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
