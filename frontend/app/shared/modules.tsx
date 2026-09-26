"use client";
import { useEffect, useRef, useState } from "react";
import Shell from "../../components/Shell";
import { Badge, Empty, ErrorBox } from "../../components/ui";
import { api, fmtMinor } from "../../lib/api";
import { keycloak, parseSession, keepFresh } from "../../lib/auth";
import { setTokenGetter } from "../../lib/api";
import { setRefreshFn } from "../../lib/api";
import { setSession } from "../../lib/auth";

type Contract = { id: string; code: string; title: string; status: string; endDate: string; valueMinor: number; currency: string };
type PO = { id: string; code: string; status: string; totalMinor: number };
type Doc = { id: string; filename: string; sizeBytes: number; status: string };

async function boot(setErr: (m: string) => void, fn: () => Promise<void>): Promise<() => void> {
  const kc = keycloak();
  try {
    const ok = await kc.init({ onLoad: "login-required", pkceMethod: "S256", checkLoginIframe: false });
    if (!ok) { setErr("Sign-in required."); return () => {}; }
    const s = parseSession(kc);
    if (!s?.tenant) { setErr("Token carries no tenant."); return () => {}; }
    setSession({ token: s.token, name: s.name, tenant: s.tenant, roles: s.roles });
    setTokenGetter(() => keycloak().token);
    setRefreshFn(async () => {
      try {
        await keycloak().updateToken(60);
        const ns = parseSession(keycloak());
        if (ns) setSession(ns);
        return true;
      } catch {
        return false;
      }
    });
    const stop = keepFresh(kc, () => setErr("Session expired — please sign in again."));
    await fn();
    return stop;
  } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Load failed"); return () => {}; }
}

export function ContractsPage() {
  const [rows, setRows] = useState<Contract[]>([]);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [more, setMore] = useState(false);
  const [stack, setStack] = useState<string[]>([]);
  async function load(cur: string) {
    setLoading(true);
    try {
      const r = await api<Contract[]>(`/api/v1/contracts?limit=15&cursor=${encodeURIComponent(cur)}`);
      setRows(r.data || []);
      setMore(!!r.pagination?.hasMore);
      setNextCursor(r.pagination?.nextCursor || "");
      setCursor(cur);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Load failed"); }
    setLoading(false);
  }
  useEffect(() => {
    let stop = () => {};
    boot(setErr, () => load("")).then((s) => (stop = s));
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <Shell><div className="pagehead"><div><h1>Contracts</h1><p>Repository with obligations and expiry roll.</p></div></div>
      {err ? <ErrorBox message={err} /> : null}
      {loading ? <div className="skel" /> : rows.length === 0 ? <Empty title="No contracts yet" /> : (<>
        <table className="grid"><thead><tr><th>Code</th><th>Title</th><th>Status</th><th>Ends</th><th>Value</th></tr></thead>
          <tbody>{rows.map((c) => (<tr key={c.id}><td className="mono">{c.code}</td><td>{c.title}</td>
            <td><Badge tone={c.status === "active" ? "ok" : c.status === "expiring" ? "warn" : undefined}>{c.status}</Badge></td>
            <td className="mono">{c.endDate || "—"}</td><td className="num">{fmtMinor(c.valueMinor, c.currency)}</td></tr>))}</tbody></table>
        <div className="pager">
          <button className="ghost" disabled={stack.length === 0} onClick={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv); }}>← Prev</button>
          <button className="ghost" disabled={!more} onClick={async () => { setStack((s) => [...s, cursor]); await load(nextCursor); }}>Next →</button>
        </div></>)}
    </Shell>
  );
}

export function OrdersPage() {
  const [rows, setRows] = useState<PO[]>([]);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [more, setMore] = useState(false);
  const [stack, setStack] = useState<string[]>([]);
  async function load(cur: string) {
    setLoading(true);
    try {
      const r = await api<PO[]>(`/api/v1/purchase-orders?limit=15&cursor=${encodeURIComponent(cur)}`);
      setRows(r.data || []);
      setMore(!!r.pagination?.hasMore);
      setNextCursor(r.pagination?.nextCursor || "");
      setCursor(cur);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Load failed"); }
    setLoading(false);
  }
  useEffect(() => {
    let stop = () => {};
    boot(setErr, () => load("")).then((s) => (stop = s));
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <Shell><div className="pagehead"><div><h1>Purchase orders</h1><p>Lifecycle with tiered approvals and 3-way match.</p></div></div>
      {err ? <ErrorBox message={err} /> : null}
      {loading ? <div className="skel" /> : rows.length === 0 ? <Empty title="No purchase orders yet" /> : (<>
        <table className="grid"><thead><tr><th>Code</th><th>Status</th><th>Total</th></tr></thead>
          <tbody>{rows.map((o) => (<tr key={o.id}><td className="mono">{o.code}</td><td><Badge>{o.status}</Badge></td><td className="num">{fmtMinor(o.totalMinor)}</td></tr>))}</tbody></table>
        <div className="pager">
          <button className="ghost" disabled={stack.length === 0} onClick={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv); }}>← Prev</button>
          <button className="ghost" disabled={!more} onClick={async () => { setStack((s) => [...s, cursor]); await load(nextCursor); }}>Next →</button>
        </div></>)}
    </Shell>
  );
}

export function SpendPage() {
  const [s, setS] = useState<{ poTotalMinor: number; invoicedTotalMinor: number; savedMinor: number; bySupplier: { supplierId: string; poTotalMinor: number; poCount: number }[] } | null>(null);
  const [intel, setIntel] = useState<{ cube: { supplierId: string; categoryId: string; currency: string; totalMinor: number; poCount: number }[]; leakage: { id: string; code: string; totalMinor: number }[]; leakageTotalMinor: number; maverick: { id: string; code: string; totalMinor: number }[]; maverickTotalMinor: number; concentration: { topShareBp: number; topSupplier: string; singleSourceRisk: boolean } } | null>(null);
  const [cases, setCases] = useState<{ id: string; item: string; baselineMinor: number; quotedMinor: number; varianceBp: number; samples: number; status: string }[]>([]);
  const [err, setErr] = useState("");
  const [calc, setCalc] = useState({ material: "10000", labor: "2500", overhead: "1500", logistics: "500", margin: "1000", quoted: "" });
  const [calcOut, setCalcOut] = useState<string>("");
  useEffect(() => {
    let stop = () => {};
    boot(setErr, async () => {
      setS((await api<typeof s>("/api/v1/spend/summary")).data);
      setIntel((await api<typeof intel>("/api/v1/spend/intelligence")).data);
      setCases((await api<typeof cases>("/api/v1/spend/price-cases?status=open")).data || []);
    }).then((s) => (stop = s));
    return () => stop();
  }, []);
  async function runCalc() {
    try {
      const pct = (v: string) => Math.round(parseFloat(v || "0") * 100); // % -> basis points
      const r = await api<{ breakdown: { should_minor: number }; gap?: { gap_minor: number; verdict: string } }>("/api/v1/spend/should-cost", {
        method: "POST",
        body: JSON.stringify({
          material_minor: Math.round(parseFloat(calc.material || "0") * 100),
          labor_minor: Math.round(parseFloat(calc.labor || "0") * 100),
          overhead_bp: pct(calc.overhead), logistics_minor: Math.round(parseFloat(calc.logistics || "0") * 100),
          margin_bp: pct(calc.margin),
          ...(calc.quoted ? { quoted_minor: Math.round(parseFloat(calc.quoted) * 100) } : {}),
        }),
      });
      setCalcOut(`should-cost ${fmtMinor(r.data.breakdown.should_minor)}${r.data.gap ? ` — gap ${fmtMinor(r.data.gap.gap_minor)} (${r.data.gap.verdict})` : ""}`);
    } catch (e: unknown) { setCalcOut(e instanceof Error ? e.message : "Calc failed"); }
  }
  async function resolve(id: string, st: string) {
    try {
      const key = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${id}`;
      await api(`/api/v1/spend/price-cases/${id}/resolve`, { method: "POST", body: JSON.stringify({ status: st }), idemKey: key });
      setCases((await api<typeof cases>("/api/v1/spend/price-cases?status=open")).data || []);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Resolve failed"); }
  }
  return (
    <Shell><div className="pagehead"><div><h1>Spend intelligence</h1><p>Ledger aggregates, leakage, maverick, should-cost.</p></div></div>
      {err ? <ErrorBox message={err} /> : null}
      {!s ? <Empty title="No spend posted" hint="Approved POs and invoices will aggregate here." /> : (<>
        <div className="cards">
          <div className="card"><div className="k">Committed</div><div className="v mono">{fmtMinor(s.poTotalMinor)}</div></div>
          <div className="card"><div className="k">Invoiced</div><div className="v mono">{fmtMinor(s.invoicedTotalMinor)}</div></div>
          <div className="card"><div className="k">Saved (awards)</div><div className="v mono good">{fmtMinor(s.savedMinor)}</div></div>
          <div className="card"><div className="k">Leakage</div><div className={`v mono ${(intel?.leakageTotalMinor || 0) > 0 ? "bad" : "good"}`}>{fmtMinor(intel?.leakageTotalMinor || 0)}</div></div>
        </div>
        {intel && intel.concentration.singleSourceRisk ? <ErrorBox message={`Single-source risk: ${intel.concentration.topSupplier} holds ${(intel.concentration.topShareBp / 100).toFixed(1)}% of spend.`} /> : null}
        <h2>Price anomalies {cases.length ? <Badge tone="warn">{cases.length} open</Badge> : null}</h2>
        {cases.length === 0 ? <Empty title="No open price cases" /> : (
          <table className="grid"><thead><tr><th>Item</th><th>Baseline</th><th>Quoted</th><th>Variance</th><th></th></tr></thead>
            <tbody>{cases.map((p) => (<tr key={p.id}><td>{p.item}</td><td className="num">{fmtMinor(p.baselineMinor)}</td>
              <td className="num">{fmtMinor(p.quotedMinor)}</td><td className="num">{p.varianceBp < 0 ? "−" : "+"}{(Math.abs(p.varianceBp) / 100).toFixed(1)}%</td>
              <td><button className="ghost" onClick={() => resolve(p.id, "handed_off")}>Hand off</button> <button className="ghost" onClick={() => resolve(p.id, "dismissed")}>Dismiss</button></td></tr>))}</tbody></table>)}
        <h2 style={{ marginTop: 20 }}>Should-cost calculator</h2>
        <p style={{ color: "var(--muted)", fontSize: 12 }}>Money in major units (e.g. 100.00); overhead/margin in <strong>percent</strong> (10 = 10%). Integer minor units on the wire.</p>
        <div className="toolbar">
          {[["material", "Material"], ["labor", "Labor"], ["overhead", "Overhead %"], ["logistics", "Logistics"], ["margin", "Margin %"], ["quoted", "Quote?"]].map(([k, label]) => (
            <label key={k} style={{ display: "flex", flexDirection: "column", fontSize: 12 }}>{label}
              <input type="text" style={{ width: 110 }} value={calc[k as keyof typeof calc]} onChange={(e) => setCalc({ ...calc, [k]: e.target.value })} aria-label={label} />
            </label>
          ))}
          <button onClick={runCalc}>Calculate</button>
        </div>
        {calcOut ? <div className="card mono">{calcOut}</div> : null}
        <h2 style={{ marginTop: 20 }}>Spend cube</h2>
        {!intel || intel.cube.length === 0 ? <Empty title="Cube is empty" /> : (
          <table className="grid"><thead><tr><th>Supplier</th><th>Category</th><th>POs</th><th>Total</th></tr></thead>
            <tbody>{intel.cube.map((r, i) => (<tr key={i}><td className="mono">{r.supplierId.slice(0, 8)}</td><td>{r.categoryId}</td><td className="num">{r.poCount}</td><td className="num">{fmtMinor(r.totalMinor, r.currency)}</td></tr>))}</tbody></table>)}
      </>)}
    </Shell>
  );
}

export function DocumentsPage() {
  const [rows, setRows] = useState<Doc[]>([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    let stop = () => {};
    boot(setErr, async () => setRows((await api<Doc[]>("/api/v1/documents?limit=25")).data || [])).then((s) => (stop = s));
    return () => stop();
  }, []);
  async function upload(f: File) {
    const kc = keycloak();
    const fd = new FormData();
    fd.append("file", f);
    const idem = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}`;
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/documents`, {
      method: "POST",
      headers: { Authorization: `Bearer ${kc.token}`, "Idempotency-Key": idem },
      body: fd,
    });
    const rid = res.headers.get("X-Request-ID") || "";
    if (!res.ok) {
      let msg = `Upload failed (${res.status})`;
      try {
        const body = await res.json();
        if (body?.error?.message) msg = `${body.error.message}${rid ? ` [${rid}]` : ""}`;
      } catch { /* non-JSON error — keep status text */ }
      setErr(msg);
      return;
    }
    setRows((await api<Doc[]>("/api/v1/documents?limit=25")).data || []);
  }
  return (
    <Shell><div className="pagehead"><div><h1>Documents</h1><p>Hash-verified store — PDF, DOCX, XLSX, CSV, images.</p></div></div>
      {err ? <ErrorBox message={err} /> : null}
      <div className="toolbar"><input type="file" aria-label="Upload document" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} /></div>
      {rows.length === 0 ? <Empty title="No documents yet" /> : (
        <table className="grid"><thead><tr><th>File</th><th>Size</th><th>Status</th></tr></thead>
          <tbody>{rows.map((d) => (<tr key={d.id}><td>{d.filename}</td><td className="num">{(d.sizeBytes / 1024).toFixed(1)} KB</td><td><Badge tone={d.status === "ready" ? "ok" : undefined}>{d.status}</Badge></td></tr>))}</tbody></table>)}
    </Shell>
  );
}


