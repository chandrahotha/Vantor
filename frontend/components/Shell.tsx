"use client";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import CommandPalette from "./CommandPalette";
import { toggleTheme } from "./ThemeInit";
import { api } from "../lib/api";
import { getSession, isDemoSession, logout, subscribeSession, type Session } from "../lib/auth";

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
  if (unread === 0) return <span className="badge">0</span>;
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
  const pageName = PAGE_NAMES[base] ?? "VANTOR";
  const isDemo = isDemoSession() || shown?.tenant === "demo";

  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>

      <nav className="side" aria-label="Primary">
        <div className="brand">
          <Image src="/icons/mark-64.png" alt="VANTOR" width={26} height={26} style={{ borderRadius: 7 }} />
          <span>
            VANTOR
            <small>by Digi Tracks</small>
          </span>
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
              >
                <span className="nav-icon" aria-hidden="true">{icon}</span>
                <span className="nav-label">{label}</span>
              </Link>
            ))}
          </div>
        ))}

        <div className="section-label">Account</div>
        <Link href="/notifications" className={base === "/notifications" ? "active" : undefined} aria-current={base === "/notifications" ? "page" : undefined}>
          <span className="nav-icon" aria-hidden="true">◆</span>
          <span className="nav-label">Alerts</span>
          <Bell />
        </Link>

        <div className="foot">
          {shown ? (
            <div className="userchip-card">
              <div className="userchip-main">
                <div className="userchip-name">
                  <span>{shown.name}</span>
                  {isDemo ? <span className="demo-badge">DEMO</span> : null}
                </div>
                <div className="userchip-meta">tenant: <span className="mono">{shown.tenant}</span></div>
              </div>
              <button
                type="button"
                className="userchip-logout"
                onClick={() => logout()}
                title="Sign out / switch workspace"
              >
                Sign out
              </button>
            </div>
          ) : (
            <div className="userchip">Not signed in</div>
          )}
          <a href="https://github.com/chandrahotha/Vantor" target="_blank" rel="noreferrer">Source · AGPL-3.0</a>
        </div>
      </nav>

      <main className="main" id="main" tabIndex={-1}>
        <div className="topbar">
          <div className="crumbs">
            VANTOR <span aria-hidden="true">/</span> <b>{pageName}</b>
          </div>
          {isDemo ? (
            <span className="topbar-demo-pill">Demo Mode</span>
          ) : (
            <span className="topbar-live-pill"><span className="status-dot" aria-hidden="true" /> Live</span>
          )}
          <div className="spacer" />
          <button
            className="search-trigger"
            onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))}
            aria-label="Open command palette"
            aria-keyshortcuts="Control+K"
          >
            <span aria-hidden="true">⌕</span> Search or command <kbd>Ctrl</kbd><kbd>K</kbd>
          </button>
          <ThemeToggle />
        </div>
        {children}
      </main>

      <CommandPalette />
    </div>
  );
}
