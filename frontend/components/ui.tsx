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
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";
import {
  clearBounces,
  getSession,
  initOnce,
  isLooping,
  keepFresh,
  keycloak,
  login,
  noteBounce,
  setSession,
  subscribeSession,
  wireSession,
} from "../lib/auth";
import { setRefreshFn, setTokenGetter, setUnauthorizedHandler } from "../lib/api";

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

/** Single OIDC entry point for every page.
 *
 * The rule this encodes: a session exists if and only if the IdP returned a
 * signed token carrying a tenant, and the page's data is loaded if and only if
 * such a session exists. There is no path here that reaches `ok` without a
 * verified identity, and none that calls `load` without one — so no panel can
 * render a number the backend never sent for a signed-in tenant.
 *
 * `check-sso` (not `login-required`) is what keeps the window from navigating
 * to the IdP on load. keycloak-js falls through to a full-window
 * `prompt=none` redirect unless `silentCheckSsoRedirectUri` is set, which is
 * the redirect loop this boot exists to avoid.
 */
export function useBoot(load: () => Promise<void>) {
  const [state, setState] = useState<BootState>("loading");
  const [error, setError] = useState("");
  const loadRef = useRef(load);
  // A 401 during the first load is definitive — the token is already dead — so
  // it must not be overwritten by the boot's own `setState("ok")` a tick later.
  const unauthorized = useRef(false);

  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let disposed = false;
    const kc = keycloak();

    /** A 401 that survives a real refresh attempt means the session is dead,
     *  not that one request failed. Drop it — leaving a session in place would
     *  leave the UI claiming to be signed in while every call 401s.
     *
     *  Idempotent, because `setSession(null)` notifies this hook's own
     *  subscriber synchronously and that subscriber ends the session too. */
    const endSession = () => {
      if (unauthorized.current) return;
      unauthorized.current = true;
      setSession(null);
      if (disposed) return;
      setError("");
      setState("signin");
    };
    setUnauthorizedHandler(endSession);
    // Re-read the session on every request rather than capturing a token once:
    // a refresh replaces it, and a captured value would go stale and 401.
    setTokenGetter(() => getSession()?.token);
    // `api()` retries once through this after a 401. Without it the retry is a
    // no-op and a merely-expired token is indistinguishable from a dead one.
    setRefreshFn(() => kc.updateToken(60).then(() => true).catch(() => false));

    if (isLooping()) {
      // Deferred by a microtask: this reads sessionStorage, and setting state
      // synchronously in the effect body would cascade a render before the
      // first paint.
      queueMicrotask(() => {
        if (disposed) return;
        setError("Sign-in is looping — the identity provider or client is misconfigured.");
        setState("error");
      });
      return () => setUnauthorizedHandler(null);
    }

    const stopFresh = keepFresh(kc, endSession);

    const showSignIn = () => {
      noteBounce(false);
      if (!disposed && !unauthorized.current) setState("signin");
    };

    (async () => {
      try {
        await initOnce(kc, {
          onLoad: "check-sso",
          pkceMethod: "S256",
          checkLoginIframe: true,
          silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
        });
      } catch (e: unknown) {
        if (!disposed) {
          setError(e instanceof Error ? e.message : "Identity provider unreachable");
          setState("error");
        }
        return;
      }
      if (disposed || unauthorized.current) return;

      if (!kc.authenticated) {
        showSignIn();
        return;
      }

      const session = wireSession(kc);
      if (!session) {
        // Authenticated, but the token names no tenant. The backend answers 403
        // for this token, so a guessed tenant would only defer the failure.
        setError("This identity has no tenant claim, so no data can be scoped to it.");
        setState("error");
        return;
      }

      noteBounce(true);
      clearBounces();
      try {
        await loadRef.current();
      } catch (e: unknown) {
        // A failed *load* is not an identity problem. The gate must not swallow
        // it: the page reaches `ok` and renders its own ErrorBox, because the
        // session is valid and only that one request failed.
        if (!disposed) setError(e instanceof Error ? e.message : "Load failed");
      }
      if (!disposed && !unauthorized.current) {
        setState("ok");
        document.documentElement.dataset.booted = "true";
      }
    })();

    const unsubscribe = subscribeSession((s) => {
      if (s && !disposed && !unauthorized.current) setState("ok");
      if (!s && !disposed) endSession();
    });

    return () => {
      disposed = true;
      stopFresh();
      unsubscribe();
      setUnauthorizedHandler(null);
    };
  }, []);

  const reload = useCallback(async () => {
    setError("");
    setState("loading");
    try {
      await loadRef.current();
      setState("ok");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Reload failed");
      setState("error");
    }
  }, []);

  return { state, error, reload };
}

/** Full-viewport authentication and state boundary.
 *
 * Replaces the page rather than sitting below it. It used to be inlined into
 * thirteen pages *after* the page head, forms and toolbars, and at
 * `min-height: 100vh` that put the sign-in card underneath the whole
 * application chrome — a signed-out visitor saw a populated dashboard with a
 * sign-in screen scrolled below it. */
export function AuthScreen({ state, error, onRetry }: { state: BootState; error?: string; onRetry?: () => void }) {
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
          <p className="authscreen-sub">Checking your enterprise identity.</p>
          <div className="authscreen-loader-bar"><div className="authscreen-loader-fill" /></div>
        </div>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="authscreen" role="alert">
        <div className="authscreen-card">
          <div className="authscreen-mark-wrap">
            <Image src="/icons/icon-192.png" alt="VANTOR" width={68} height={68} className="authscreen-mark-img" priority />
          </div>
          <div className="authscreen-badge">ENTERPRISE PROCUREMENT OS</div>
          <h1 className="authscreen-title">Sign-in problem</h1>
          <p className="authscreen-sub">
            {error || "The identity provider could not be reached."}
          </p>
          <div className="authscreen-actions">
            {/* Retry re-runs the boot in place. It must not navigate to the IdP:
                a transient network failure is not a request to authenticate. */}
            {onRetry ? (
              <Button variant="primary" onClick={onRetry}>
                Try again
              </Button>
            ) : null}
            <Button variant="secondary" onClick={() => login()}>
              Sign in with Vantor ID
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="authscreen" role="status">
      <div className="authscreen-card">
        <div className="authscreen-mark-wrap">
          <Image src="/icons/icon-192.png" alt="VANTOR" width={68} height={68} className="authscreen-mark-img" priority />
        </div>
        <div className="authscreen-badge">ENTERPRISE PROCUREMENT OS</div>
        <h1 className="authscreen-title">Sign in to VANTOR</h1>
        <p className="authscreen-sub">
          Autonomous spend governance, supplier intelligence, and contract workflows.
        </p>
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

/* ------------------------------------------------------------------------- *
 * Grade-5 design system — VANTOR_MAX_AI_WORKKIT/12_FRONTEND_GRADE5.
 *
 * Every primitive below follows one rule: colour is never the only signal.
 * Tone is carried in a class or a data attribute for styling, and the meaning
 * is always carried in text — the accessible name, the role, or a signed value.
 * A red button that says "Reject" is safe; a red button with a glyph and no
 * label is not, and neither is a badge whose only difference is its hue.
 * ------------------------------------------------------------------------- */

/** The status vocabulary used by badges and the timeline. */
export type Tone = "ok" | "warn" | "bad" | "info";
/** The metric vocabulary, which matches `StatCard`: a metric is good or bad,
 *  where a status is merely not-warning. */
export type MetricTone = "good" | "bad" | "warn";

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  className,
  children,
  disabled,
  ...rest
}: {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "success";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={["btn", `btn-${variant}`, `btn-${size}`, className].filter(Boolean).join(" ")}
      // The label stays mounted while loading, so the button does not resize and
      // shift the layout out from under the cursor mid-request.
      aria-busy={loading || undefined}
      disabled={disabled || loading}
    >
      {children}
    </button>
  );
}

/** A glyph-only control still needs a name. The glyph is `aria-hidden`; the
 *  label is not optional, which is what stops an icon-only button from
 *  shipping as an unlabelled control. */
export function IconButton({
  label,
  icon,
  className,
  ...rest
}: { label: string; icon: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button {...rest} aria-label={label} title={label} className={["iconbtn", className].filter(Boolean).join(" ")}>
      <span aria-hidden="true">{icon}</span>
    </button>
  );
}

export type SegmentedOption<T extends string> = { value: T; label: string };

/** A radiogroup with a roving tab index.
 *
 * One tab stop, arrow keys to move, and the selection is announced by
 * `aria-checked` — so the state is legible to a screen reader and to anyone
 * who cannot see which segment is lit. */
export function Segmented<T extends string>({ label, value, options, onChange, className }: {
  label: string;
  value: T;
  options: SegmentedOption<T>[];
  onChange: (value: T) => void;
  className?: string;
}) {
  const selected = Math.max(0, options.findIndex((o) => o.value === value));

  const move = (delta: number) => {
    const next = (selected + delta + options.length) % options.length;
    onChange(options[next].value);
  };

  return (
    <div role="radiogroup" aria-label={label} className={["segmented", className].filter(Boolean).join(" ")}>
      {options.map((o, i) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={i === selected}
          tabIndex={i === selected ? 0 : -1}
          className={`segmented-item${i === selected ? " is-selected" : ""}`}
          onClick={() => onChange(o.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(1); }
            if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(-1); }
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
}

export function Drawer({ open, title, onClose, children }: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEscape(open, onClose);
  if (!open) return null;
  return (
    <div className="drawer-scrim" onClick={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="drawer-head">
          <h2 className="drawer-title">{title}</h2>
          <IconButton label="Close panel" icon="✕" onClick={onClose} />
        </header>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}

/** Confirmation for an action that books money, locks a record, or is otherwise
 *  not undoable from this screen. An `alertdialog`, because it interrupts, and
 *  the body names the consequence in words rather than leaving the user to
 *  infer it from the button's colour. */
export function ConfirmDialog({ open, title, body, confirmLabel, busy, onConfirm, onCancel }: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEscape(open, onCancel);
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div
        className="modal-container"
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2 className="modal-title">{title}</h2>
        </div>
        <div className="modal-body">
          <div className="confirm-body">{body}</div>
        </div>
        <div className="modal-footer">
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" loading={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

export type ToastTone = "ok" | "warn" | "bad" | "info";
type ToastFn = (tone: ToastTone, message: string) => void;
const ToastContext = createContext<ToastFn>(() => {});

export function useToast(): ToastFn {
  return useContext(ToastContext);
}

type ToastItem = { id: number; tone: ToastTone; message: string };

/** Mounted above every page by `components/AppProviders`, which has to be an
 *  ancestor of the pages rather than of `Shell` — `Shell` is rendered *by* a
 *  page, so a provider inside it would be a descendant of its own consumer. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(0);

  const push = useCallback<ToastFn>((tone, message) => {
    const id = ++next.current;
    setItems((prev) => [...prev, { id, tone, message }]);
    setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 6000);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toast-region">
        {items.map((t) => (
          // A failure is an alert, not a status: an error the user never
          // perceives is an error they will act on later, wrongly.
          <div
            key={t.id}
            className={`toast toast-${t.tone}`}
            role={t.tone === "bad" ? "alert" : "status"}
            data-tone={t.tone}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** A single number, with its direction and its meaning.
 *
 * `trend` renders as a *signed* value with an arrow glyph, never as a colour
 * change alone; `hint` is a real tooltip, so the number explains itself to
 * anyone who asks rather than only to whoever wrote the dashboard. */
export function MetricCard({ label, value, tone, hint, trend }: {
  label: string;
  value: string;
  tone?: MetricTone;
  hint?: string;
  trend?: { value: string; dir: "up" | "down" };
}) {
  return (
    <div className="metric" data-tone={tone}>
      <div className="metric-label">
        {label}
        {hint ? <span className="metric-hint" role="tooltip" aria-label={`${label}: definition`}>{hint}</span> : null}
      </div>
      <div className={`metric-value mono${tone ? ` ${tone}` : ""}`}>{value}</div>
      {trend ? (
        <div className="metric-trend" data-dir={trend.dir}>
          <span aria-hidden="true">{trend.dir === "down" ? "▼" : "▲"}</span> {trend.value}
        </div>
      ) : null}
    </div>
  );
}

/** A bar is not a number. `aria-valuenow` is what makes it readable, and the
 *  clamp keeps a bad figure from rendering a bar that overflows its track. */
export function Progress({ value, label }: { value: number; label: string }) {
  const clamped = Math.min(100, Math.max(0, Math.round(value)));
  return (
    <div
      className="progress"
      role="progressbar"
      aria-label={label}
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="progress-fill" style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function FilterBar({ children, className }: { children: ReactNode; className?: string }) {
  return <div role="search" className={["filterbar", className].filter(Boolean).join(" ")}>{children}</div>;
}

export function Timeline({ items }: {
  items: { title: string; meta?: string; tone?: Tone }[];
}) {
  if (items.length === 0) {
    return <div className="timeline-empty" role="status">No activity yet</div>;
  }
  return (
    <ol className="timeline">
      {items.map((it, i) => (
        <li key={`${it.title}-${i}`} className="timeline-item" data-tone={it.tone}>
          <div className="timeline-title">{it.title}</div>
          {it.meta ? <div className="timeline-meta">{it.meta}</div> : null}
        </li>
      ))}
    </ol>
  );
}
