"use client";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import CommandPalette from "./CommandPalette";
import { ConfirmDialog } from "./ui";
import { toggleTheme } from "./ThemeInit";
import { api } from "../lib/api";
import { getSession, logout, signIn, subscribeSession, type Session } from "../lib/auth";

const NAV: { section?: string; items: [icon: string, label: string, href: string][] }[] = [
  {
    section: "Workspaces",
    items: [
      ["◈", "Dashboard", "/"],
      ["◉", "Suppliers", "/suppliers"],
      ["◇", "RFQs", "/rfqs"],
      ["▣", "Contracts", "/contracts"],
      ["◫", "Purchase orders", "/orders"],
    ],
  },
  {
    section: "Request & negotiate",
    items: [
      ["◬", "Requisitions", "/requisitions"],
      // VNT-045. The approval queue had no route of its own and rendered only
      // inside the copilot page. It is the surface a manager uses most, and it
      // governs money, so it is now where it belongs - and the section order
      // follows the process rather than the org chart: request, approve, then buy.
      ["✓", "Approvals", "/approvals"],
      ["⇄", "Negotiation simulator", "/negosim"],
    ],
  },
  {
    section: "Intelligence",
    items: [
      ["▤", "Spend", "/spend"],
      ["▥", "Documents", "/documents"],
      ["✳", "Governance", "/governance"],
      ["◊", "Integrations", "/integrations"],
      ["◐", "Copilot", "/copilot"],
    ],
  },
];

const PAGE_NAMES: Record<string, string> = Object.fromEntries(
  NAV.flatMap((g) => g.items).map(([, label, href]) => [href, label]).concat([["/notifications", "Alerts"]]),
);

/** The crumb trail for a path.
 *
 *  This used to be a single `PAGE_NAMES[path] ?? "VANTOR"` lookup, which only
 *  ever matched an exact nav href. On `/suppliers/<id>` — the one route in the
 *  app that is reached *from* another screen — nothing matched, so the header
 *  read "VANTOR / VANTOR": the user was told neither where they were nor what
 *  they had drilled into. A detail route now names its parent, and the parent
 *  is a link, so there is always a way back up that does not rely on the
 *  browser's Back button. */
function crumbsFor(path: string): { label: string; href?: string }[] {
  const exact = PAGE_NAMES[path];
  if (exact) return [{ label: exact }];
  const parent = Object.keys(PAGE_NAMES)
    .filter((href) => href !== "/" && path.startsWith(href + "/"))
    .sort((a, b) => b.length - a.length)[0];
  if (parent) return [{ label: PAGE_NAMES[parent], href: parent }, { label: "Details" }];
  return [{ label: "VANTOR" }];
}

function Bell() {
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const r = await api<{ unread: number }>("/api/v1/notifications/unread-count");
        if (!stop) setUnread(r.data.unread);
      } catch { /* unauthenticated or offline — bell stays quiet */ }
    }
    poll();
    const id = setInterval(poll, 30000);
    return () => { stop = true; clearInterval(id); };
  }, []);
  // A permanent "0" chip on the nav item is noise: it draws the eye to the one
  // state that needs no attention, and on the cobalt sidebar it rendered as a
  // washed-out smear. Nothing to report, nothing shown.
  if (unread === 0) return null;
  return <span className="badge bad" aria-label={`${unread} unread alerts`}>{unread}</span>;
}

function ThemeToggle() {
  // Derived from the DOM attribute, updated via MutationObserver so this
  // tracks ThemeInit (which sets it on mount) and any other toggle — no
  // setState-in-effect, no hydration mismatch (server renders dark=false).
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const el = document.documentElement;
    const read = () => setDark(el.dataset.theme === "dark");
    read();
    const mo = new MutationObserver(read);
    mo.observe(el, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);
  return (
    <button
      className="icon"
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={dark}
      title={dark ? "Light mode" : "Dark mode"}
      onClick={() => setDark(toggleTheme() === "dark")}
    >
      {dark ? "☀" : "☾"}
    </button>
  );
}

export default function Shell({ children, user }: { children: ReactNode; user?: { name: string; tenant: string } }) {
  const path = usePathname();
  const base = path.split("?")[0];
  const [session, setSessionState] = useState<Session | null>(() => getSession());
  useEffect(() => subscribeSession(setSessionState), []);
  const shown = user ?? (session ? { name: session.name, tenant: session.tenant } : undefined);
  const crumbs = crumbsFor(base);

  // Off-canvas navigation for the drawer layout (<= 960px). Above that the
  // stylesheet ignores `data-open` entirely and the sidebar is always visible,
  // so this state is inert on a desktop and needs no media-query listener.
  const [navOpen, setNavOpen] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);

  // Escape closes it and returns focus to the control that opened it — a panel
  // that traps a keyboard user is worse than no panel.
  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setNavOpen(false); toggleRef.current?.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navOpen]);

  /** Signing out discards unsaved form state on every open panel and returns to
   *  the identity provider, so it is confirmed rather than one stray click. */
  const [confirmSignOut, setConfirmSignOut] = useState(false);

  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>

      {navOpen ? (
        <button
          type="button"
          className="nav-scrim"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
        />
      ) : null}

      <nav id="primary-nav" className="side" aria-label="Primary" data-open={navOpen ? "true" : "false"}>
        <div className="brand brand-logo-full">
          {/* `unoptimized`: this is a fixed-size brand mark, already shipped at
              exactly 2x its painted size, so the optimizer has nothing to gain
              — and routing it through `/_next/image` made the one element on
              every single screen depend on an image-transform request that can
              fail or time out. When it did, the sidebar rendered as an empty
              white plate with no logo in it. A static file from `public/`
              cannot fail that way. */}
          <Image
            src="/vantor-logo.png"
            alt="VANTOR"
            width={220}
            height={65}
            unoptimized
            style={{ width: "100%", height: "auto", maxHeight: "48px", objectFit: "contain" }}
            priority
          />
        </div>

        {NAV.map((group) => (
          <div key={group.section}>
            <div className="section-label">{group.section}</div>
            {group.items.map(([icon, label, href]) => (
              <Link
                key={href}
                href={href}
                className={base === href || (href !== "/" && base.startsWith(href + "/")) ? "active" : undefined}
                aria-current={base === href ? "page" : undefined}
                // Navigating is the whole purpose of the drawer, so following a
                // link closes it; otherwise the destination renders behind a
                // panel the user then has to dismiss by hand.
                onClick={() => setNavOpen(false)}
              >
                <span className="nav-icon" aria-hidden="true">{icon}</span>
                <span className="nav-label">{label}</span>
              </Link>
            ))}
          </div>
        ))}

        <div className="section-label">Account</div>
        <Link href="/notifications" className={base === "/notifications" ? "active" : undefined} aria-current={base === "/notifications" ? "page" : undefined} onClick={() => setNavOpen(false)}>
          <span className="nav-icon" aria-hidden="true">◆</span>
          <span className="nav-label">Alerts</span>
          <Bell />
        </Link>

        <div className="foot">
          {shown ? (
            <div className="userchip-card">
              <div className="userchip-avatar" aria-hidden="true">
                {(shown.name.replace(/\s*\(Bypass\)/i, "").trim() || "AD").slice(0, 2).toUpperCase()}
              </div>
              <div className="userchip-info">
                {/* `title` restores what the CSS ellipsis takes away: the
                    sidebar is a fixed 248px and a real tenant's name or
                    tenant slug routinely overflows it, with nothing before
                    this that let a user confirm which account "Administra…"
                    actually was short for. */}
                <div className="userchip-name" title={shown.name.replace(/\s*\(Bypass\)/i, "").trim() || "Administrator"}>
                  {shown.name.replace(/\s*\(Bypass\)/i, "").trim() || "Administrator"}
                </div>
                <div className="userchip-tenant" title={shown.tenant}>{shown.tenant}</div>
              </div>
              <button
                type="button"
                className="userchip-logout"
                onClick={() => setConfirmSignOut(true)}
                title="Sign out of current workspace"
              >
                Sign out
              </button>
            </div>
          ) : (
            <div className="userchip-unauth">
              <div className="userchip-unauth-text">Not signed in</div>
              <button
                type="button"
                className="userchip-signin-btn"
                onClick={() => { void signIn(); }}
              >
                <span aria-hidden="true">🔑</span> Sign in
              </button>
            </div>
          )}
          <div className="foot-links">
            <a href="https://github.com/chandrahotha/Vantor" target="_blank" rel="noreferrer">
              Source · Apache-2.0
            </a>
          </div>
        </div>
      </nav>

      <main className="main" id="main" tabIndex={-1}>
        <div className="topbar">
          <button
            ref={toggleRef}
            type="button"
            className="nav-toggle"
            aria-label={navOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={navOpen}
            aria-controls="primary-nav"
            onClick={() => setNavOpen((v) => !v)}
          >
            <span aria-hidden="true">{navOpen ? "✕" : "☰"}</span>
          </button>
          <nav className="crumbs" aria-label="Breadcrumb">
            <Link href="/">VANTOR</Link>
            {crumbs.map((c) => (
              <span key={c.label}>
                <span aria-hidden="true"> / </span>
                {c.href ? <Link href={c.href}>{c.label}</Link> : <b aria-current="page">{c.label}</b>}
              </span>
            ))}
          </nav>
          <span className="topbar-live-pill"><span className="status-dot" aria-hidden="true" /> Live</span>
          <div className="spacer" />
          {!shown ? (
            <button
              type="button"
              className="topbar-signin-btn"
              onClick={() => { void signIn(); }}
            >
              <span aria-hidden="true">🔑</span> Sign in
            </button>
          ) : null}
          <button
            className="search-trigger"
            onClick={() => window.dispatchEvent(new CustomEvent("vantor:open-palette"))}
            aria-label="Open command palette"
            aria-keyshortcuts="Control+K"
          >
            <span aria-hidden="true">⌕</span>
            <span className="search-trigger-label">Search or command</span>
            <kbd>Ctrl</kbd><kbd>K</kbd>
          </button>
          <ThemeToggle />
        </div>
        {children}
      </main>

      <CommandPalette />

      <ConfirmDialog
        open={confirmSignOut}
        title="Sign out of VANTOR?"
        confirmLabel="Sign out"
        onCancel={() => setConfirmSignOut(false)}
        onConfirm={() => { setConfirmSignOut(false); logout(); }}
        body={
          <>
            You will be returned to the identity provider. Anything typed into a form
            on this screen and not yet saved is discarded.
          </>
        }
      />
    </div>
  );
}
