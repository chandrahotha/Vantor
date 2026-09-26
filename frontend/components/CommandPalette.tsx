"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../lib/api";

type Hit = { kind: string; id: string; label: string; href?: string };

const PAGES: Hit[] = [
  { kind: "Go", id: "nav-dash", label: "Go to Dashboard", href: "/" },
  { kind: "Go", id: "nav-sup", label: "Go to Suppliers", href: "/suppliers" },
  { kind: "Go", id: "nav-rfq", label: "Go to RFQs", href: "/rfqs" },
  { kind: "Go", id: "nav-con", label: "Go to Contracts", href: "/contracts" },
  { kind: "Go", id: "nav-po", label: "Go to Purchase orders", href: "/orders" },
  { kind: "Go", id: "nav-spend", label: "Go to Spend", href: "/spend" },
  { kind: "Go", id: "nav-doc", label: "Go to Documents", href: "/documents" },
  { kind: "Go", id: "nav-ai", label: "Go to Copilot", href: "/copilot" },
];

/** Command palette — Ctrl/⌘+K. Real navigation + live supplier search. No fake entries. */
export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>(PAGES);
  const [active, setActive] = useState(0);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queryId = useRef(0);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQ("");
      setHits(PAGES);
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open ]);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (!open) return;
    if (q.trim().length < 2) {
      setHits(PAGES.filter((p) => p.label.toLowerCase().includes(q.toLowerCase())));
      setActive(0);
      return;
    }
    timer.current = setTimeout(async () => {
      const my = ++queryId.current;
      const nav = PAGES.filter((p) => p.label.toLowerCase().includes(q.toLowerCase()));
      try {
        const r = await api<{ id: string; code: string; name: string }[]>(`/api/v1/suppliers?limit=5&search=${encodeURIComponent(q)}`);
        if (queryId.current !== my) return; // stale response loses
        const sup: Hit[] = (r.data || []).map((s) => ({ kind: "Supplier", id: s.id, label: `${s.code} — ${s.name}` }));
        setHits([...nav, ...sup]);
      } catch {
        if (queryId.current !== my) return;
        setHits(nav);
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
    <div role="dialog" aria-label="Command palette" onClick={() => setOpen(false)}
      style={{ position: "fixed", inset: 0, background: "rgba(10,25,49,.45)", zIndex: 50, paddingTop: "12vh" }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ background: "#fff", borderRadius: 12, maxWidth: 560, margin: "0 auto", overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,.3)" }}>
        <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (hits.length === 0) return;
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, hits.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
            else if (e.key === "Enter" && hits[active]) { go(hits[active]); }
          }}
          placeholder="Type a command or search suppliers…" aria-label="Command input"
          style={{ width: "100%", border: "none", outline: "none", padding: "14px 16px", fontSize: 15 }} />
        <div style={{ maxHeight: 320, overflowY: "auto", borderTop: "1px solid #e2e8f0" }} role="listbox">
          {hits.length === 0 ? <div style={{ padding: 16, color: "#64748b" }}>No matches.</div> : hits.map((h, i) => (
            <div key={h.id} role="option" aria-selected={i === active} onClick={() => go(h)}
              style={{ padding: "10px 16px", cursor: "pointer", background: i === active ? "#eff6ff" : "#fff", display: "flex", gap: 10 }}>
              <span className="badge info">{h.kind}</span><span>{h.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
