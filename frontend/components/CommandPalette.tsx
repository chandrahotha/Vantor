"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../lib/api";

type Hit = { kind: string; id: string; label: string; hint?: string; href?: string };

const PAGES: Hit[] = [
  { kind: "Go", id: "nav-dash", label: "Go to Dashboard", hint: "Health, attention, latest POs", href: "/" },
  { kind: "Go", id: "nav-sup", label: "Go to Suppliers", hint: "Directory, search, sort", href: "/suppliers" },
    { kind: "Go", id: "nav-req", label: "Go to Requisitions", hint: "Request before you buy", href: "/requisitions" },
  { kind: "Go", id: "nav-rfq", label: "Go to RFQs", hint: "Create, quotes, compare, award", href: "/rfqs" },
  { kind: "Go", id: "nav-con", label: "Go to Contracts", hint: "Repository and expiry", href: "/contracts" },
  { kind: "Go", id: "nav-po", label: "Go to Purchase orders", hint: "Approve, send, receive, invoice", href: "/orders" },
  { kind: "Go", id: "nav-spend", label: "Go to Spend", hint: "Cube, leakage, should-cost", href: "/spend" },
  { kind: "Go", id: "nav-doc", label: "Go to Documents", hint: "Upload, extract, search", href: "/documents" },
  { kind: "Go", id: "nav-gov", label: "Go to Governance", hint: "Audit chain, catalog, budgets", href: "/governance" },
  { kind: "Go", id: "nav-alert", label: "Go to Alerts", hint: "Awards, approvals, expiries", href: "/notifications" },
  { kind: "Go", id: "nav-ai", label: "Go to Copilot", hint: "Evidence-cited AI answers", href: "/copilot" },
];

/** Command palette â€” Ctrl/âŒ˜+K. Real navigation + live supplier search. */
export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [supHits, setSupHits] = useState<Hit[]>([]);
  const [active, setActive] = useState(0);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queryId = useRef(0);

  const nav = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return PAGES.filter((p) => p.label.toLowerCase().includes(needle) || (p.hint ?? "").toLowerCase().includes(needle));
  }, [q]);
  const hits = q.trim().length < 2 ? nav : [...nav, ...supHits];
  const activeIdx = hits.length === 0 ? 0 : Math.min(active, hits.length - 1);

  function show() {
    setQ(""); setSupHits([]); setActive(0); setOpen(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) setOpen(false); else show();
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // `open` is read but not tracked on purpose: re-subscribing on every toggle is
    // pure overhead, and `show()` is a no-op when the palette is already open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!open) return;
    if (timer.current) clearTimeout(timer.current);
    if (q.trim().length < 2) return;
    timer.current = setTimeout(async () => {
      const my = ++queryId.current;
      try {
        const r = await api<{ id: string; code: string; name: string }[]>(`/api/v1/suppliers?limit=5&search=${encodeURIComponent(q)}`);
        if (queryId.current !== my) return;
        setSupHits((r.data || []).map((s) => ({ kind: "Supplier", id: s.id, label: `${s.code} â€” ${s.name}` })));
      } catch {
        if (queryId.current !== my) return;
        setSupHits([]);
      }
      setActive(0);
    }, 220);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [q, open]);

  function go(h: Hit) {
    setOpen(false);
    if (h.href) router.push(h.href);
    else if (h.kind === "Supplier") router.push(`/suppliers?highlight=${encodeURIComponent(h.id)}`);
  }

  if (!open) return null;
  return (
    <div
      className="palette-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      onClick={() => setOpen(false)}
    >
      <div className="palette-panel" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="palette-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          role="combobox"
          aria-expanded="true"
          aria-controls="palette-listbox"
          aria-label="Search or run a command"
          aria-activedescendant={hits[activeIdx] ? `palette-opt-${hits[activeIdx].id}` : undefined}
          onKeyDown={(e) => {
            if (hits.length === 0) return;
            if (e.key === "ArrowDown") { e.preventDefault(); setActive(Math.min(activeIdx + 1, hits.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setActive(Math.max(activeIdx - 1, 0)); }
            else if (e.key === "Enter" && hits[activeIdx]) { go(hits[activeIdx]); }
          }}
          placeholder="Search suppliers or jump to a workspaceâ€¦"
        />
        <div id="palette-listbox" className="palette-list" role="listbox">
          {hits.length === 0 ? (
            <div style={{ padding: 18, color: "var(--faint)", fontSize: "var(--fs-13)" }}>No matches.</div>
          ) : (
            hits.map((h, i) => (
              <div
                key={h.id}
                id={`palette-opt-${h.id}`}
                role="option"
                aria-selected={i === activeIdx}
                className={`palette-item${i === activeIdx ? " active" : ""}`}
                onClick={() => go(h)}
                onMouseEnter={() => setActive(i)}
              >
                <span className={`badge ${h.kind === "Supplier" ? "ok" : "info"}`}>{h.kind}</span>
                <span>
                  {h.label}
                  {h.hint ? <span style={{ color: "var(--faint)", marginLeft: 8, fontSize: "var(--fs-11)" }}>{h.hint}</span> : null}
                </span>
              </div>
            ))
          )}
        </div>
        <div className="palette-foot">
          <span><kbd>â†‘â†“</kbd> move</span>
          <span><kbd>â†µ</kbd> open</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
