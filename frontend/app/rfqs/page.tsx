"use client";
import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { Badge, Empty, ErrorBox } from "../../components/ui";
import { api, fmtMinor } from "../../lib/api";
import { keycloak, parseSession, keepFresh, setSession } from "../../lib/auth";
import { setTokenGetter, setRefreshFn } from "../../lib/api";

type Rfq = { id: string; code: string; title: string; status: string };
type Comp = { quoteId: string; supplierName: string; status: string; totalMinor: number };

export default function Rfqs() {
  const [rows, setRows] = useState<Rfq[]>([]);
  const [sel, setSel] = useState<{ rfq: Rfq; comp: Comp[] } | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [more, setMore] = useState(false);
  const [stack, setStack] = useState<string[]>([]);

  async function load(cur: string) {
    setLoading(true);
    try {
      const r = await api<Rfq[]>(`/api/v1/rfqs?limit=15&cursor=${encodeURIComponent(cur)}`);
      setRows(r.data || []);
      setMore(!!r.pagination?.hasMore);
      setNextCursor(r.pagination?.nextCursor || "");
      setCursor(cur);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Load failed"); }
    setLoading(false);
  }

  useEffect(() => {
    let stop = () => {};
    const kc = keycloak();
    kc.init({ onLoad: "login-required", pkceMethod: "S256", checkLoginIframe: false }).then(async (ok) => {
      if (!ok) { setErr("Sign-in required."); setLoading(false); return; }
      stop = keepFresh(kc, () => setErr("Session expired - please sign in again."));
      const s = parseSession(kc);
      if (!s?.tenant) { setErr("Token carries no tenant."); setLoading(false); return; }
      setTokenGetter(() => keycloak().token); const __s = parseSession(keycloak()); if (__s) setSession({ token: __s.token, name: __s.name, tenant: __s.tenant, roles: __s.roles }); setRefreshFn(async () => { try { await keycloak().updateToken(60); return true; } catch { return false; } });
      await load("");
    }).catch(() => { setErr("Keycloak unreachable."); setLoading(false); });
    return () => stop();
  }, []);

  async function open(r: Rfq) {
    try {
      const c = await api<Comp[]>(`/api/v1/rfqs/${r.id}/comparison`);
      setSel({ rfq: r, comp: c.data || [] });
    } catch (e: unknown) { setSel(null); setErr(e instanceof Error ? e.message : "Load failed"); }
  }

  return (
    <Shell>
      <div className="pagehead"><div><h1>RFQs</h1><p>Comparison totals are server-computed from real quote lines.</p></div></div>
      {err ? <ErrorBox message={err} /> : null}
      {loading ? <div className="skel" /> : rows.length === 0 ? <Empty title="No RFQs yet" /> : (<>
        <table className="grid"><thead><tr><th>Code</th><th>Title</th><th>Status</th><th></th></tr></thead>
          <tbody>{rows.map((r) => (<tr key={r.id}><td className="mono">{r.code}</td><td>{r.title}</td>
            <td><Badge tone={r.status === "awarded" ? "ok" : "info"}>{r.status}</Badge></td>
            <td><button className="ghost" onClick={() => open(r)}>Compare</button></td></tr>))}</tbody></table>
        <div className="pager">
          <button className="ghost" disabled={stack.length === 0} onClick={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv); }}>← Prev</button>
          <button className="ghost" disabled={!more} onClick={async () => { setStack((s) => [...s, cursor]); await load(nextCursor); }}>Next →</button>
        </div></>)}
      {sel ? (<><h2>Comparison — {sel.rfq.code}</h2>
        <table className="grid"><thead><tr><th>Supplier</th><th>Status</th><th>Total</th></tr></thead>
          <tbody>{sel.comp.map((q) => (<tr key={q.quoteId}><td>{q.supplierName}</td><td><Badge>{q.status}</Badge></td><td className="num">{fmtMinor(q.totalMinor)}</td></tr>))}</tbody></table></> ) : null}
    </Shell>
  );
}


