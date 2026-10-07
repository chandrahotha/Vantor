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
import Link from "next/link";
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
import { fetchPersonas, getSession, keepFresh, restoreSession, setSession, signIn, signInDemo, subscribeSession, type Persona } from "../lib/auth";
import { setRefreshFn, setTokenGetter, setUnauthorizedHandler } from "../lib/api";
import Shell from "./Shell";

export function Badge({ tone, children }: { tone?: "ok" | "warn" | "bad" | "info"; children: React.ReactNode }) {
  return <span className={`badge${tone ? ` ${tone}` : ""}`}>{children}</span>;
}

/** A money figure in a data column.
 *
 *  `fmtMinor` returns "1,250.00 INR" as one string, so a right-aligned column
 *  aligned on the last character of the ISO code and the decimal points landed
 *  wherever the integer part left them. Splitting the code into a fixed-width
 *  cell puts every amount on the same right edge and every code on the same
 *  left edge, which is what makes a column of money scannable.
 *
 *  Takes the already-formatted string so there is exactly one money formatter
 *  in the app and this stays a presentation concern.
 */
export function Money({ children }: { children: string }) {
  const m = /^(.*) ([A-Z]{3})$/.exec(children);
  if (!m) return <>{children}</>;
  return (
    <>
      {m[1]} <span className="ccy">{m[2]}</span>
    </>
  );
}

//: Only `supplier` has its own detail route (`/suppliers/[id]`). The others
//: list-only pages with no per-id route yet, so a reference to one of them
//: links to the list rather than a dead URL — still strictly better than the
//: bare/truncated id this replaces, and upgrades for free the day those routes
//: exist, because every caller goes through here instead of hand-rolling the
//: href.
const ENTITY_LIST_PATH: Record<string, string> = {
  supplier: "/suppliers",
  contract: "/contracts",
  po: "/orders",
  invoice: "/orders",
  rfq: "/rfqs",
};

/** A link to another entity, with a human-readable label instead of a bare id.
 *
 *  Every cross-entity reference in the product (a PO's supplier, a contract's
 *  supplier, an RFQ's winning bidder, ...) renders through here, so "which
 *  supplier" is always a name and a click rather than a UUID. `name` is
 *  optional — while it hasn't resolved yet this falls back to the id itself
 *  rather than rendering nothing.
 */
export function EntityLink({ kind, id, name }: { kind: keyof typeof ENTITY_LIST_PATH; id: string; name?: string }) {
  if (!id) return <span className="muted">—</span>;
  const base = ENTITY_LIST_PATH[kind];
  const label = name || id;
  return kind === "supplier" ? (
    <Link href={`${base}/${id}`}>{label}</Link>
  ) : (
    <Link href={base} title={`Open ${kind} ${id} in the list below`}>{label}</Link>
  );
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
      <button disabled={busy || stack.length === 0} onClick={onPrev}>← Prev</button>
      <span className="mono" style={{ fontSize: 12 }}>page {stack.length + 1}</span>
      <button disabled={busy || !hasMore} onClick={onNext}>Next →</button>
    </div>
  );
}

export type Column<T> = {
  key: string;
  header: string;
  /** Money columns must be rendered via `fmtMinor` with a currency, never raw. */
  numeric?: boolean;
  /** Right-align a non-numeric column — an action cluster, typically.
   *
   *  This exists because several pages were laying their action buttons out
   *  with an inline `justifyContent: "flex-end"` while the `<th>` above them
   *  stayed left-aligned, so the column header and its contents sat at opposite
   *  ends of the same column. Alignment is a property of the column, so it is
   *  declared once and applied to the header and the cells together. */
  align?: "end";
  sortable?: boolean;
  render: (row: T) => React.ReactNode;
};

function cellClass<T>(c: Column<T>): string | undefined {
  if (c.numeric) return "num";
  return c.align === "end" ? "col-end" : undefined;
}

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
    // The wrapper scrolls horizontally on a narrow viewport. A scrollable region
    // that only a mouse can reach fails WCAG 2.1.1, so it is focusable and
    // named — a keyboard user tabs to it and scrolls it with the arrow keys.
    <div className="gridwrap" role="region" aria-label={caption} tabIndex={0}>
      <table className="grid">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => {
              const active = sort === c.key;
              const ariaSort = active ? (order === "asc" ? "ascending" : "descending") : c.sortable ? "none" : undefined;
              return (
                <th key={c.key} scope="col" aria-sort={ariaSort} className={cellClass(c)}>
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
                <td key={c.key} className={cellClass(c)}>{c.render(r)}</td>
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

    /** A 401 means the token the app holds is not one the API will accept.
     *  Drop it — leaving a session in place would leave the UI claiming to be
     *  signed in while every panel errors. */
    const endSession = () => {
      if (unauthorized.current) return;
      unauthorized.current = true;
      setSession(null);
      if (disposed) return;
      setError("");
      setState("signin");
    };
    setUnauthorizedHandler(endSession);
    const onUnauth = () => endSession();
    if (typeof window !== "undefined") {
      window.addEventListener("vantor:unauthorized", onUnauth);
    }
    // Read the session per request rather than capturing a token once: a
    // renewal replaces it, and a captured value would go stale and 401.
    setTokenGetter(() => getSession()?.token);
    // There is no refresh grant to exchange — a local session is renewed by
    // asking for a new one — so a 401 is final and the retry is a no-op.
    setRefreshFn(async () => false);

    const stopFresh = keepFresh(endSession);

    (async () => {
      // A session already in hand (this tab, or a previous one) is adopted
      // without asking the server for another. This is what stops a reload, a
      // Fast Refresh, or switching to another window and back from dropping
      // the user onto the sign-in screen.
      const session = restoreSession();
      if (!session) {
        if (!disposed) setState("signin");
        return;
      }
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
      if (typeof window !== "undefined") {
        window.removeEventListener("vantor:unauthorized", onUnauth);
      }
    };
  }, []);

  const reload = useCallback(async () => {
    setError("");
    setState("loading");
    unauthorized.current = false;
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
    if (getSession()) {
      return (
        <Shell>
          <div className="pagehead">
            <div>
              <div className="skel" style={{ width: 160, height: 32, marginBottom: 12, borderRadius: 4 }} />
              <div className="skel" style={{ width: 400, height: 20, borderRadius: 4 }} />
            </div>
          </div>
          <Skeleton rows={6} />
        </Shell>
      );
    }
    return (
      <main className="authscreen">
        <div className="authscreen-card" role="status" aria-live="polite">
          <div className="authscreen-mark-wrap">
            <Image src="/icons/icon-192.png" alt="VANTOR" width={68} height={68} unoptimized className="authscreen-mark-img" priority />
            <div className="authscreen-pulse" />
          </div>
          <div className="authscreen-badge">VANTOR ENTERPRISE SUITE</div>
          <h1 className="authscreen-title">Opening VANTOR…</h1>
          <p className="authscreen-sub">Checking your enterprise identity.</p>
          <div className="authscreen-loader-bar"><div className="authscreen-loader-fill" /></div>
        </div>
      </main>
    );
  }

  if (state === "error") {
    return (
      <main className="authscreen">
        <div className="authscreen-card" role="alert">
          <div className="authscreen-mark-wrap">
            <Image src="/icons/icon-192.png" alt="VANTOR" width={68} height={68} unoptimized className="authscreen-mark-img" priority />
          </div>
          <div className="authscreen-badge">ENTERPRISE PROCUREMENT OS</div>
          <h1 className="authscreen-title">Sign-in problem</h1>
          <p className="authscreen-sub">
            {error || "The identity provider could not be reached."}
          </p>
          <div className="authscreen-actions">
            {/* Retry re-runs the boot in place. There is no second "sign in"
                button beside it any more: sign-in is one action, and offering
                it twice — once as a retry and once as a redirect — was how the
                old screen ended up sending people to an identity provider that
                was not running. */}
            {onRetry ? (
              <Button variant="primary" onClick={onRetry}>
                Try again
              </Button>
            ) : null}
          </div>
        </div>
      </main>
    );
  }

  return <SignInCard onSignedIn={onRetry} />;
}

/** The sign-in screen: one button, no credentials.
 *
 *  Sign-in is a single request to this product's own API, so the screen asks
 *  for nothing and explains nothing the user cannot act on. What it must do is
 *  report failure honestly — the previous version redirected to an identity
 *  provider and, when that host was down, the user left the app entirely and
 *  landed on the browser's "can't reach this page". A failed sign-in now stays
 *  here and says which address could not be reached.
 */
function SignInCard({ onSignedIn }: { onSignedIn?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState("");
  // Populated only under AUTH_MODE=local; stays empty (and the picker stays
  // hidden) under OIDC, when the API is unreachable, or in a test that mocks
  // fetch for a different endpoint — fetchPersonas() never throws for that.
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [persona, setPersona] = useState("");

  useEffect(() => {
    const ctrl = new AbortController();
    fetchPersonas(ctrl.signal).then((list) => {
      if (list.length > 1) {
        setPersonas(list);
        setPersona((cur) => cur || list[0].key);
      }
    });
    return () => ctrl.abort();
  }, []);

  async function enter() {
    setBusy(true);
    setFailed("");
    try {
      await signIn(persona || undefined);
      onSignedIn?.();
    } catch (e: unknown) {
      setFailed(e instanceof Error ? e.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  function enterDemo() {
    signInDemo(persona || undefined);
    onSignedIn?.();
  }

  return (
    <main className="authscreen">
      <div className="authscreen-card" role="status">
        <div className="authscreen-mark-wrap">
          <Image src="/icons/icon-192.png" alt="VANTOR" width={68} height={68} unoptimized className="authscreen-mark-img" priority />
        </div>
        <div className="authscreen-badge">PROCUREMENT OS</div>
        <h1 className="authscreen-title">VANTOR</h1>
        <p className="authscreen-sub">
          Suppliers, sourcing, contracts, orders and spend — in one place.
        </p>

        {failed ? (
          <div className="authscreen-error-box" role="alert">
            <span className="authscreen-alert-icon" aria-hidden="true">!</span>
            <span className="authscreen-alert-content">
              <span className="authscreen-alert-msg">{failed}</span>
              <button
                type="button"
                onClick={enterDemo}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  marginTop: "10px",
                  padding: "8px 14px",
                  backgroundColor: "rgba(59, 130, 246, 0.25)",
                  border: "1px solid rgba(147, 197, 253, 0.5)",
                  borderRadius: "6px",
                  color: "#ffffff",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                <span>✨</span>
                <span>Continue in Demo Mode (No backend needed) →</span>
              </button>
            </span>
          </div>
        ) : null}

        {personas.length > 1 ? (
          <label className="authscreen-persona">
            <span className="authscreen-persona-label">Enter as</span>
            <select
              value={persona}
              onChange={(e) => setPersona(e.target.value)}
              disabled={busy}
              aria-label="Local identity to sign in as"
            >
              {personas.map((p) => (
                <option key={p.key} value={p.key}>{p.label}</option>
              ))}
            </select>
          </label>
        ) : null}

        <div className="authscreen-actions">
          <button
            type="button"
            className="authscreen-cta"
            onClick={enter}
            disabled={busy}
            aria-busy={busy || undefined}
          >
            <span className="authscreen-cta-icon" aria-hidden="true">→</span>
            <div className="authscreen-cta-text">
              <span className="authscreen-cta-headline">
                {busy ? "Opening your workspace…" : "Log in to VANTOR"}
              </span>
              <small className="authscreen-cta-sub">No password needed on this deployment</small>
            </div>
          </button>
        </div>

        <div style={{ marginTop: "14px", textAlign: "center" }}>
          <button
            type="button"
            onClick={enterDemo}
            style={{
              background: "none",
              border: "none",
              color: "rgba(255, 255, 255, 0.65)",
              fontSize: "13px",
              cursor: "pointer",
              textDecoration: "underline",
              padding: "4px 8px",
            }}
          >
            Explore in Demo Mode (Preview without backend) ✨
          </button>
        </div>
      </div>
    </main>
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
 * Grade-5 design system — docs/05-frontend/grade5/DESIGN_SYSTEM.md.
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

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

/** Everything a modal owes a keyboard user, in one place.
 *
 *  `Drawer` and `ConfirmDialog` both declared `aria-modal="true"` while doing
 *  none of what that attribute promises: focus stayed on the button behind the
 *  scrim, Tab walked straight out of the dialog into the page underneath, the
 *  page behind kept scrolling, and dismissing the dialog left focus on nothing.
 *  A screen reader was told the rest of the page was inert; it was not.
 *
 *  Returns the ref to put on the dialog container.
 */
function useModal(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    returnFocus.current = (document.activeElement as HTMLElement) ?? null;

    // Move focus in. Prefer the first real control; fall back to the container,
    // which is why it carries tabIndex={-1}.
    const node = ref.current;
    const first = node?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? node)?.focus();

    // The page behind a modal must not scroll out from under it.
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab" || !node) return;
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE))
        .filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (items.length === 0) { e.preventDefault(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      returnFocus.current?.focus?.();
    };
  }, [open, onClose]);

  return ref;
}

export function Drawer({ open, title, onClose, children }: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useModal(open, onClose);
  if (!open) return null;
  return (
    <div className="drawer-scrim" onClick={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        ref={ref as unknown as React.Ref<HTMLElement>}
        tabIndex={-1}
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
export function ConfirmDialog({ open, title, body, confirmLabel, busy, tone = "primary", onConfirm, onCancel }: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  /** `danger` for a final state — terminate, reject, expire. The dialog always
   *  painted its confirm button in the primary fill, so "Terminate" and
   *  "Approve" were the same colour on the same control. Colour is never the
   *  only signal here: the label is still a verb and the body still names the
   *  consequence in words. */
  tone?: "primary" | "danger";
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useModal(open, onCancel);
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div
        className="modal-container"
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        ref={ref}
        tabIndex={-1}
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
          <Button variant={tone === "danger" ? "danger" : "primary"} loading={busy} onClick={onConfirm}>
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
let metricSeq = 0;

export function MetricCard({ label, value, tone, hint, trend }: {
  label: string;
  value: string;
  tone?: MetricTone;
  hint?: string;
  trend?: { value: string; dir: "up" | "down" };
}) {
  // Stable per instance, for `aria-describedby`.
  const [hintId] = useState(() => `metric-hint-${++metricSeq}`);
  return (
    <div className="metric" data-tone={tone} aria-describedby={hint ? hintId : undefined}>
      <div className="metric-label">{label}</div>
      <div className={`metric-value mono${tone ? ` ${tone}` : ""}`}>{value}</div>
      {trend ? (
        <div className="metric-trend" data-dir={trend.dir}>
          <span aria-hidden="true">{trend.dir === "down" ? "▼" : "▲"}</span> {trend.value}
        </div>
      ) : null}
      {/* The definition stays visible text rather than becoming a hover
          tooltip: a number whose meaning is only available to a mouse is a
          number half the users cannot check. What changed is where it sits. It
          used to be a flex sibling of the label inside `.metric-label`, a row
          that is 11px, uppercase and letter-spaced for a two-word caption — so
          a full sentence of definition wrapped through the middle of every tile
          and pushed the figure around. It is its own line now, in sentence
          case, under the value it describes, and wired to the tile with
          `aria-describedby` instead of the `role="tooltip"` it carried before,
          which claims to be a popup and was never one. */}
      {hint ? <p className="metric-hint" id={hintId}>{hint}</p> : null}
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
