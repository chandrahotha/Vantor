"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import CommandPalette from "./CommandPalette";
import { api } from "../lib/api";
import { getSession, subscribeSession, type Session } from "../lib/auth";

const NAV = [
  ["Dashboard", "/"],
  ["Suppliers", "/suppliers"],
  ["RFQs", "/rfqs"],
  ["Contracts", "/contracts"],
  ["Purchase orders", "/orders"],
  ["Spend", "/spend"],
  ["Documents", "/documents"],
  ["Copilot", "/copilot"],
  ["Alerts", "/notifications"],
];

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
    const id = setInterval(poll, 30000); // honest polling; push lands later
    return () => { stop = true; clearInterval(id); };
  }, []);
  if (unread === 0) return null;
  return <span className="badge bad" aria-label={`${unread} unread alerts`}>{unread}</span>;
}

export default function Shell({ children, user }: { children: ReactNode; user?: { name: string; tenant: string } }) {
  const path = usePathname();
  const base = path.split("?")[0];
  const [session, setSessionState] = useState<Session | null>(() => getSession());
  useEffect(() => subscribeSession(setSessionState), []);
  const shown = user ?? (session ? { name: session.name, tenant: session.tenant } : undefined);
  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <nav className="side" aria-label="Primary">
        <div className="brand">VANTOR <span style={{ fontWeight: 400, color: "#7d8aa3", fontSize: 12 }}>by Digi Tracks</span></div>
        {NAV.map(([label, href]) => (
          <Link key={href} href={href} className={base === href || (href !== "/" && base.startsWith(href + "/")) ? "active" : ""}>
            {label}{href === "/notifications" ? (<> <Bell /></>) : null}
          </Link>
        ))}
        <div className="foot">
          {shown ? <div>{shown.name}<br />tenant: {shown.tenant}</div> : <div>Not signed in</div>}
          <div style={{ marginTop: 8 }}>digi.tracks@outlook.com</div>
          <div style={{ marginTop: 4 }}><a href="https://github.com/chandrahotha/Vantor" target="_blank" rel="noreferrer">Source (AGPL-3.0)</a></div>
        </div>
      </nav>
      <main className="main" id="main" tabIndex={-1}>{children}</main>
      <div style={{ position: "fixed", bottom: 14, right: 16, zIndex: 40 }}>
        <button className="kbd" style={{ cursor: "pointer", border: "none" }} onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))} aria-label="Open command palette (Control K)">
          Ctrl K
        </button>
      </div>
      <CommandPalette />
    </div>
  );
}
