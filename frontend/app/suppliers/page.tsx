"use client";
import { useEffect, useRef, useState } from "react";
import Shell from "../../components/Shell";
import { Badge, Empty, ErrorBox } from "../../components/ui";
import { api } from "../../lib/api";
import { keycloak, parseSession, keepFresh, setSession } from "../../lib/auth";
import { setTokenGetter, setRefreshFn } from "../../lib/api";

type Supplier = { id: string; code: string; name: string; status: string; country: string; currency: string };

export default function Suppliers() {
  const [rows, setRows] = useState<Supplier[]>([]);
  const [page, setPage] = useState<{ nextCursor: string; hasMore: boolean }>({ nextCursor: "", hasMore: false });
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("created_at");
  const [order, setOrder] = useState("desc");
  const [cursor, setCursor] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [highlight, setHighlight] = useState("");
  const busy = useRef(false);
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({});

  useEffect(() => {
    if (!highlight || rows.length === 0) return;
    const el = rowRefs.current[highlight];
    if (el) {
      el.scrollIntoView({ block: "center" });
      el.focus?.();
      const t = setTimeout(() => setHighlight(""), 4000);
      return () => clearTimeout(t);
    }
  }, [highlight, rows]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, { score?: { score: number; grade: string; risk_tier: string } | null; certs?: { name: string; status: string }[]; qual?: { status: string; exists: boolean } }>>({});

  async function load(cur: string, q: string, s: string, o: string) {
    if (busy.current) return; // last-wins race guard for pager double-clicks
    busy.current = true;
    setLoading(true); setErr("");
    try {
      const r = await api<Supplier[]>(`/api/v1/suppliers?limit=15&cursor=${encodeURIComponent(cur)}&search=${encodeURIComponent(q)}&sort=${s}&order=${o}`);
      setRows(r.data || []); setPage({ nextCursor: r.pagination?.nextCursor || "", hasMore: !!r.pagination?.hasMore });
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Load failed"); }
    busy.current = false;
    setLoading(false);
  }

  useEffect(() => {
    let stop = () => {};
    // Palette deep-link: ?highlight=<supplier-id> jumps straight to the row.
    try {
      const hid = new URLSearchParams(window.location.search).get("highlight") || "";
      if (hid) { setHighlight(hid); setSearch(""); }
    } catch { /* non-browser — ignore */ }
    const kc = keycloak();
    kc.init({ onLoad: "login-required", pkceMethod: "S256", checkLoginIframe: false })
      .then((ok) => {
        if (!ok) { setErr("Sign-in required."); setLoading(false); return; }
        stop = keepFresh(kc, () => setErr("Session expired - please sign in again."));
        const s = parseSession(kc);
        if (!s?.tenant) { setErr("Token carries no tenant — access refused."); setLoading(false); return; }
        setTokenGetter(() => keycloak().token); const __s = parseSession(keycloak()); if (__s) setSession({ token: __s.token, name: __s.name, tenant: __s.tenant, roles: __s.roles }); setRefreshFn(async () => { try { await keycloak().updateToken(60); return true; } catch { return false; } });
        load("", "", sort, order);
      })
      .catch(() => { setErr("Keycloak unreachable."); setLoading(false); });
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function next() { if (page.hasMore) { setStack([...stack, cursor]); const nx = page.nextCursor; setCursor(nx); load(nx, search, sort, order); } }
  function prev() { const st = [...stack]; const pv = st.pop() || ""; setStack(st); setCursor(pv); load(pv, search, sort, order); }
  function resort(col: string) {
    const o = sort === col && order === "desc" ? "asc" : "desc";
    setSort(col); setOrder(o); setCursor(""); setStack([]); load("", search, col, o);
  }

  return (
    <Shell>
      <div className="pagehead"><div><h1>Suppliers</h1><p>Server-paginated grid — search, sort and pages hit the API.</p></div></div>
      {err ? <ErrorBox message={err} /> : null}
      <div className="toolbar" role="search">
        <input type="search" placeholder="Search code or name…" value={search} aria-label="Search suppliers"
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { setCursor(""); setStack([]); load("", search, sort, order); } }} />
        <button className="ghost" onClick={() => { setCursor(""); setStack([]); load("", search, sort, order); }}>Search</button>
      </div>
      {loading ? <div className="skel" /> : rows.length === 0 ? <Empty title="No suppliers found" hint="Create suppliers via the API or adjust search." /> : (
        <>
          <table className="grid">
            <thead><tr>
              <th><button onClick={() => resort("code")}>Code {sort === "code" ? (order === "desc" ? "↓" : "↑") : ""}</button></th>
              <th><button onClick={() => resort("name")}>Name {sort === "name" ? (order === "desc" ? "↓" : "↑") : ""}</button></th>
              <th><button onClick={() => resort("status")}>Status {sort === "status" ? (order === "desc" ? "↓" : "↑") : ""}</button></th>
              <th>Country</th><th>Currency</th>
            </tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id} ref={(el) => { rowRefs.current[r.id] = el; }} tabIndex={r.id === highlight ? 0 : undefined} style={r.id === highlight ? { background: "#eff6ff" } : undefined}><td className="mono">{r.code}</td><td>{r.name}{r.id === highlight ? (<span className="badge info">from palette</span>) : null}</td>
                <td><Badge tone={r.status === "active" ? "ok" : r.status === "blocked" ? "bad" : undefined}>{r.status}</Badge></td>
                <td>{r.country || "—"}</td><td>{r.currency || "—"}</td></tr>
            ))}</tbody>
          </table>
          <div className="pager">
            <button className="ghost" disabled={stack.length === 0} onClick={prev}>← Prev</button>
            <button className="ghost" disabled={!page.hasMore} onClick={next}>Next →</button>
          </div>
        </>
      )}
    </Shell>
  );
}


