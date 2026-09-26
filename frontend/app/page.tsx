"use client";
import { useEffect, useState } from "react";
import Shell from "../components/Shell";
import { Badge, Empty, ErrorBox } from "../components/ui";
import { api, fmtMinor } from "../lib/api";
import { keycloak, parseSession, keepFresh, setSession } from "../lib/auth";
import { setTokenGetter, setRefreshFn } from "../lib/api";

type Summary = { poTotalMinor: number; invoicedTotalMinor: number; bySupplier: { supplierId: string; currency: string; poTotalMinor: number; poCount: number }[] };
type Contract = { id: string; code: string; title: string; endDate: string };
type Rfq = { id: string; code: string; title: string; status: string };
type PO = { id: string; code: string; status: string; totalMinor: number };

export default function Dashboard() {
  const [ready, setReady] = useState<"loading" | "signin" | "error" | "ok">("loading");
  const [err, setErr] = useState("");
  const [user, setUser] = useState<{ name: string; tenant: string } | undefined>();
  const [spend, setSpend] = useState<Summary | null>(null);
  const [expiring, setExpiring] = useState<Contract[]>([]);
  const [rfqs, setRfqs] = useState<Rfq[]>([]);
  const [orders, setOrders] = useState<PO[]>([]);

  useEffect(() => {
    let stop = () => {};
    const kc = keycloak();
    kc.init({ onLoad: "login-required", pkceMethod: "S256", checkLoginIframe: false })
      .then(async (ok) => {
        if (!ok) { setReady("signin"); return; }
        stop = keepFresh(kc, () => setErr("Session expired - please sign in again."));
        const s = parseSession(kc);
        if (!s) { setReady("error"); setErr("Signed in but token carries no identity."); return; }
        if (!s.tenant) { setReady("error"); setErr("Token carries no tenant — access refused."); return; }
        setTokenGetter(() => keycloak().token); setRefreshFn(async () => { try { await keycloak().updateToken(60); return true; } catch { return false; } });
        setSession({ token: s.token, name: s.name, tenant: s.tenant, roles: s.roles });
        setUser({ name: s.name, tenant: s.tenant });
        try {
          const [sp, ex, rq, po] = await Promise.allSettled([
            api<Summary>("/api/v1/spend/summary"),
            api<Contract[]>("/api/v1/contracts?expiring=true&limit=5"),
            api<Rfq[]>("/api/v1/rfqs?limit=5"),
            api<PO[]>("/api/v1/purchase-orders?limit=5"),
          ]);
          if (sp.status === "fulfilled") setSpend(sp.value.data);
          if (ex.status === "fulfilled") setExpiring(ex.value.data || []);
          if (rq.status === "fulfilled") setRfqs(rq.value.data || []);
          if (po.status === "fulfilled") setOrders(po.value.data || []);
          const failed = [sp, ex, rq, po].filter((r) => r.status === "rejected");
          if (failed.length === 4) throw new Error("API unreachable - start the backend stack.");
          if (failed.length > 0) setErr("Some panels failed to load - showing partial data.");
          setReady("ok");
        } catch (e: unknown) {
          setReady("error");
          setErr(e instanceof Error ? e.message : "API unreachable — start the backend stack.");
        }
      })
      .catch(() => { setReady("error"); setErr("Keycloak unreachable — check NEXT_PUBLIC_KEYCLOAK_URL."); });
    return () => stop();
  }, []);

  if (ready === "loading") return <Shell><div className="skel" /><div className="skel" style={{ marginTop: 8 }} /></Shell>;
  if (ready === "signin" || ready === "error") return <Shell><ErrorBox message={err || "Sign-in required."} /></Shell>;

  return (
    <Shell user={user}>
      <div className="pagehead">
        <div><h1>Procurement health</h1><p>Real data only — empty means no activity yet, never placeholders.</p></div>
      </div>
      <div className="cards">
        <div className="card"><div className="k">Committed (POs)</div><div className="v mono">{spend ? fmtMinor(spend.poTotalMinor, spend.bySupplier[0]?.currency) : "—"}</div></div>
        <div className="card"><div className="k">Invoiced (approved)</div><div className="v mono">{spend ? fmtMinor(spend.invoicedTotalMinor, spend.bySupplier[0]?.currency) : "—"}</div></div>
        <div className="card"><div className="k">Contracts expiring ≤90d</div><div className={`v mono ${expiring.length ? "bad" : "good"}`}>{expiring.length}</div></div>
        <div className="card"><div className="k">Open RFQs</div><div className="v mono">{rfqs.filter((r) => ["sent", "response"].includes(r.status)).length}</div></div>
      </div>
      <h2>What needs attention</h2>
      {expiring.length === 0 && rfqs.length === 0 ? (
        <Empty title="Nothing pending" hint="Expiring contracts, open RFQs and approvals will appear here." />
      ) : (
        <table className="grid">
          <thead><tr><th>Item</th><th>Type</th><th>Status</th></tr></thead>
          <tbody>
            {expiring.map((c) => (<tr key={c.id}><td>{c.code} — {c.title}</td><td>Contract</td><td><Badge tone="warn">expiring {c.endDate}</Badge></td></tr>))}
            {rfqs.filter((r) => ["sent", "response"].includes(r.status)).map((r) => (<tr key={r.id}><td>{r.code} — {r.title}</td><td>RFQ</td><td><Badge tone="info">{r.status}</Badge></td></tr>))}
          </tbody>
        </table>
      )}
      <h2 style={{ marginTop: 20 }}>Latest purchase orders</h2>
      {orders.length === 0 ? <Empty title="No purchase orders yet" /> : (
        <table className="grid">
          <thead><tr><th>Code</th><th>Status</th><th>Total</th></tr></thead>
          <tbody>{orders.map((o) => (<tr key={o.id}><td className="mono">{o.code}</td><td><Badge>{o.status}</Badge></td><td className="num">{fmtMinor(o.totalMinor)}</td></tr>))}</tbody>
        </table>
      )}
    </Shell>
  );
}


