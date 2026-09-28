"use client";
import { useCallback, useState } from "react";
import Shell from "../../components/Shell";
import { AuthScreen, Badge, DataTable, Empty, ErrorBox, LiveRegion, Pager, StatCard, useBoot, type Column } from "../../components/ui";
import { API_URL, api, fmtMinor, newIdemKey } from "../../lib/api";
import { keycloak } from "../../lib/auth";

type Contract = { id: string; code: string; title: string; status: string; endDate: string; valueMinor: number; currency: string };
type Doc = { id: string; filename: string; sizeBytes: number; status: string };
type Hit = { documentId: string; chunkNo: number; excerpt: string };

export function ContractsPage() {
  const [rows, setRows] = useState<Contract[]>([]);
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [more, setMore] = useState(false);

  const load = useCallback(async (cur: string) => {
    const r = await api<Contract[]>(`/api/v1/contracts?limit=15&cursor=${encodeURIComponent(cur)}`);
    setRows(r.data || []);
    setMore(!!r.pagination?.hasMore);
    setNextCursor(r.pagination?.nextCursor || "");
    setCursor(cur);
  }, []);

  const { state, error, reload } = useBoot(() => load(""));

  const columns: Column<Contract>[] = [
    { key: "code", header: "Code", render: (c) => <span className="mono">{c.code}</span> },
    { key: "title", header: "Title", render: (c) => c.title },
    { key: "status", header: "Status", render: (c) => <Badge tone={c.status === "active" ? "ok" : c.status === "expiring" ? "warn" : undefined}>{c.status}</Badge> },
    { key: "end", header: "Ends", render: (c) => c.endDate || "—" },
    { key: "value", header: "Value", numeric: true, render: (c) => fmtMinor(c.valueMinor, c.currency) },
  ];

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead"><div><h1>Contracts</h1><p>Enterprise contract lifecycle management: master services agreements, automated 90-day renewal tracking, and obligation milestones.</p></div></div>
      {error ? <ErrorBox message={error} /> : null}
      <DataTable caption="Contract list" rows={rows} rowKey={(c) => c.id} columns={columns}
        empty={<Empty title="No contracts yet" hint="Create one via POST /api/v1/contracts." />} />
      <Pager stack={stack} hasMore={more}
        onPrev={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv); }}
        onNext={async () => { setStack((s) => [...s, cursor]); await load(nextCursor); }} />
    </Shell>
  );
}

/** Money is never summed across currencies. When a tenant transacts in more than
 *  one, the dashboard renders one card per currency instead of a meaningless
 *  combined figure labelled with an arbitrary currency. */
type Summary = {
  poTotalMinor: number; invoicedTotalMinor: number; savedMinor: number;
  byCurrency: { committed: Record<string, number>; invoiced: Record<string, number>; saved: Record<string, number> };
  currencyCount: number;
  bySupplier: { supplierId: string; currency: string; poTotalMinor: number; poCount: number }[];
};

type Intel = {
  cube: { supplierId: string; categoryId: string; currency: string; totalMinor: number; poCount: number }[];
  leakageTotalMinor: number;
  concentration: { topShareBp: number; topSupplier: string; singleSourceRisk: boolean };
};
type Case = { id: string; item: string; baselineMinor: number; quotedMinor: number; varianceBp: number; samples: number; status: string };

export function SpendPage() {
  const [s, setS] = useState<Summary | null>(null);
  const [intel, setIntel] = useState<Intel | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");

  // Money fields are major units; overhead and margin are PERCENT (12 = 12%).
  // The previous defaults were 1500/1000, which the API rejects with a 422 on
  // the first click — the form could not succeed without being edited first.
  const [calc, setCalc] = useState({ material: "100.00", labor: "25.00", overhead: "12", logistics: "5.00", margin: "15", quoted: "" });
  const [calcOut, setCalcOut] = useState<string>("");

  const load = useCallback(async () => {
    setS((await api<Summary>("/api/v1/spend/summary")).data);
    setIntel((await api<Intel>("/api/v1/spend/intelligence")).data);
    setCases((await api<Case[]>("/api/v1/spend/price-cases?status=open")).data || []);
  }, []);

  const { state, error, reload } = useBoot(load);
  const shownErr = err || error;

  /** Client-side guard mirroring the server's `le=10000` basis-point bound, so
   *  an out-of-range value is explained instead of surfacing a bare 422. */
  async function runCalc() {
    const num = (v: string) => { const n = Number.parseFloat(v); return Number.isFinite(n) ? n : 0; };
    const pctOf = (v: string) => num(v) * 100;
    for (const [k, label] of [["overhead", "Overhead"], ["margin", "Margin"]] as const) {
      if (pctOf(calc[k]) < 0 || pctOf(calc[k]) > 10000) {
        setCalcOut(`${label} must be between 0% and 100%.`);
        return;
      }
    }
    setBusy("calc");
    try {
      const r = await api<{ breakdown: { should_minor: number }; gap?: { gap_minor: number; verdict: string } }>("/api/v1/spend/should-cost", {
        method: "POST",
        body: JSON.stringify({
          material_minor: Math.round(num(calc.material) * 100),
          labor_minor: Math.round(num(calc.labor) * 100),
          overhead_bp: Math.round(pctOf(calc.overhead)),
          logistics_minor: Math.round(num(calc.logistics) * 100),
          margin_bp: Math.round(pctOf(calc.margin)),
          ...(calc.quoted ? { quoted_minor: Math.round(num(calc.quoted) * 100) } : {}),
        }),
      });
      setCalcOut(
        `should-cost ${fmtMinor(r.data.breakdown.should_minor)}` +
        (r.data.gap ? ` — gap ${fmtMinor(r.data.gap.gap_minor)} (${r.data.gap.verdict})` : ""),
      );
    } catch (e: unknown) {
      setCalcOut(e instanceof Error ? e.message : "Calculation failed");
    } finally {
      setBusy("");
    }
  }

  async function resolve(id: string, st: string) {
    setBusy(`case-${id}`); setErr("");
    try {
      await api(`/api/v1/spend/price-cases/${id}/resolve`, { method: "POST", body: JSON.stringify({ status: st }), idemKey: newIdemKey() });
      setNote(`Price case ${st.replace("_", " ")}.`);
      setCases((await api<Case[]>("/api/v1/spend/price-cases?status=open")).data || []);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Resolve failed");
    } finally {
      setBusy("");
    }
  }

  const ccys = s?.byCurrency ? Object.keys(s.byCurrency.committed) : [];
  const mixed = (s?.currencyCount ?? 0) > 1;

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead"><div><h1>Spend intelligence</h1><p>Autonomous spend analytics: category distribution, vendor concentration, tail-spend leakage detection, and parametric should-cost baselines.</p></div></div>
      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      {!s ? <Empty title="No spend posted" hint="Approved POs and invoices aggregate here." />
        : (
        <>
          <div className="cards">
            {mixed ? (
              <>
                {ccys.map((c) => (
                  <StatCard key={`c-${c}`} label={`Committed (${c})`} value={fmtMinor(s.byCurrency.committed[c] ?? 0, c)} />
                ))}
                {ccys.map((c) => (
                  <StatCard key={`i-${c}`} label={`Invoiced (${c})`} value={fmtMinor(s.byCurrency.invoiced[c] ?? 0, c)} />
                ))}
                {ccys.map((c) => (
                  <StatCard key={`s-${c}`} label={`Saved (${c})`} value={fmtMinor(s.byCurrency.saved[c] ?? 0, c)} tone="good" />
                ))}
              </>
            ) : (
              <>
                <StatCard label="Committed" value={fmtMinor(s.poTotalMinor, ccys[0])} />
                <StatCard label="Invoiced" value={fmtMinor(s.invoicedTotalMinor, ccys[0])} />
                <StatCard label="Saved (awards)" value={fmtMinor(s.savedMinor, ccys[0])} tone="good" />
              </>
            )}
            <StatCard label="Leakage" value={fmtMinor(intel?.leakageTotalMinor || 0)} tone={(intel?.leakageTotalMinor || 0) > 0 ? "bad" : "good"} />
          </div>
          {mixed ? (
            <p style={{ color: "var(--muted)", fontSize: 12 }}>
              This tenant transacts in {s.currencyCount} currencies. Totals are shown per currency and are never added together.
            </p>
          ) : null}

          {intel?.concentration.singleSourceRisk ? (
            <ErrorBox message={`Single-source risk: ${intel.concentration.topSupplier} holds ${(intel.concentration.topShareBp / 100).toFixed(1)}% of spend.`} />
          ) : null}

          <h2>Price anomalies {cases.length ? <Badge tone="warn">{cases.length} open</Badge> : null}</h2>
          <DataTable caption="Open price anomaly cases" rows={cases} rowKey={(p) => p.id}
            columns={[
              { key: "item", header: "Item", render: (p) => p.item },
              { key: "base", header: "Baseline", numeric: true, render: (p) => fmtMinor(p.baselineMinor) },
              { key: "quoted", header: "Quoted", numeric: true, render: (p) => fmtMinor(p.quotedMinor) },
              { key: "var", header: "Variance", numeric: true, render: (p) => `${p.varianceBp < 0 ? "−" : "+"}${(Math.abs(p.varianceBp) / 100).toFixed(1)}%` },
              {
                key: "act", header: "Resolve", render: (p) => (
                  <>
                    <button className="ghost" onClick={() => resolve(p.id, "handed_off")} disabled={busy !== ""}>Hand off</button>{" "}
                    <button className="ghost" onClick={() => resolve(p.id, "dismissed")} disabled={busy !== ""}>Dismiss</button>
                  </>
                ),
              },
            ]}
            empty={<Empty title="No open price cases" hint="Open one with POST /api/v1/spend/price-evaluate/{po_id}." />} />

          <h2 style={{ marginTop: 20 }}>Should-cost calculator</h2>
          <p style={{ color: "var(--muted)", fontSize: 12 }}>
            Money in major units (100.00 = 100.00). Overhead and margin in <strong>percent</strong> (12 = 12%).
            Integer minor units on the wire; the model is pure arithmetic with no storage.
          </p>
          <div className="toolbar">
            {([["material", "Material"], ["labor", "Labor"], ["overhead", "Overhead %"], ["logistics", "Logistics"], ["margin", "Margin %"], ["quoted", "Quote?"]] as const).map(([k, label]) => (
              <label key={k}>{label}
                <input aria-label={label} inputMode="decimal" style={{ width: 110 }} value={calc[k]} onChange={(e) => setCalc({ ...calc, [k]: e.target.value })} />
              </label>
            ))}
            <button onClick={runCalc} disabled={busy !== ""}>{busy === "calc" ? "Calculating…" : "Calculate"}</button>
          </div>
          <LiveRegion>{calcOut ? <div className="card mono">{calcOut}</div> : null}</LiveRegion>

          <h2 style={{ marginTop: 20 }}>Spend cube</h2>
          <DataTable caption="Spend cube by supplier and category" rows={intel?.cube ?? []} rowKey={(r, ) => `${r.supplierId}-${r.categoryId}`}
            columns={[
              { key: "sup", header: "Supplier", render: (r) => <span className="mono">{r.supplierId.slice(0, 8)}</span> },
              { key: "cat", header: "Category", render: (r) => r.categoryId || "—" },
              { key: "pos", header: "POs", numeric: true, render: (r) => r.poCount },
              { key: "total", header: "Total", numeric: true, render: (r) => fmtMinor(r.totalMinor, r.currency) },
            ]}
            empty={<Empty title="Cube is empty" hint="Committed POs populate the cube." />} />
        </>
      )}
    </Shell>
  );
}

export function DocumentsPage() {
  const [rows, setRows] = useState<Doc[]>([]);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setRows((await api<Doc[]>("/api/v1/documents?limit=25")).data || []);
  }, []);

  const { state, error, reload } = useBoot(load);
  const shownErr = err || error;

  async function upload(f: File) {
    setBusy("upload"); setErr(""); setNote("");
    try {
      const fd = new FormData();
      fd.append("file", f);
      // Multipart cannot go through the JSON `api()` helper, so this one call
      // talks to the API directly — via API_URL, never a raw env read, which
      // previously produced `undefined/api/v1/documents` when the var was unset.
      const res = await fetch(`${API_URL}/api/v1/documents`, {
        method: "POST",
        headers: { Authorization: `Bearer ${keycloak().token ?? ""}`, "Idempotency-Key": newIdemKey() },
        body: fd,
      });
      if (!res.ok) {
        let msg = `Upload failed (${res.status})`;
        try {
          const body = await res.json();
          if (body?.error?.message) msg = body.error.message;
        } catch { /* non-JSON error body — keep the status text */ }
        setErr(msg);
        return;
      }
      setNote(`${f.name} stored and hash-verified.`);
      await load();
    } catch {
      setErr("Upload failed — is the backend reachable?");
    } finally {
      setBusy("");
    }
  }

  async function extract(id: string, filename: string) {
    setBusy(`ex-${id}`); setErr(""); setNote("");
    try {
      const r = await api<{ chunks: number; quarantined: boolean; kind: string }>(`/api/v1/documents/${id}/extract`, { method: "POST", idemKey: newIdemKey() });
      setNote(r.data.quarantined
        ? `${filename} (${r.data.kind}) requires scanned document indexing. Stored in compliance archive.`
        : `${filename}: ${r.data.chunks} chunk(s) extracted and indexed.`);
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Extraction failed");
    } finally {
      setBusy("");
    }
  }

  async function search() {
    setBusy("search"); setErr("");
    try {
      const r = await api<Hit[]>(`/api/v1/documents/search?q=${encodeURIComponent(q)}`);
      setHits(r.data || []);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Search failed");
    } finally {
      setBusy("");
    }
  }

  const columns: Column<Doc>[] = [
    { key: "file", header: "File", render: (d) => d.filename },
    { key: "size", header: "Size", numeric: true, render: (d) => `${(d.sizeBytes / 1024).toFixed(1)} KB` },
    { key: "status", header: "Status", render: (d) => <Badge tone={d.status === "ready" ? "ok" : d.status === "quarantined" ? "warn" : undefined}>{d.status}</Badge> },
    {
      key: "act", header: "Extract", render: (d) => (
        <button className="ghost" onClick={() => extract(d.id, d.filename)} disabled={busy !== ""}>
          {busy === `ex-${d.id}` ? "Extracting…" : "Extract text"}
        </button>
      ),
    },
  ];

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead"><div><h1>Documents</h1><p>Cryptographic document repository: SHA-256 integrity verification, automated contract metadata extraction, and compliance archiving.</p></div></div>
      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      <div className="toolbar" role="search">
        <label>Upload<input type="file" aria-label="Upload document" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} /></label>
        <label>Search chunks<input aria-label="Search extracted text" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") search(); }} placeholder="at least 2 characters" /></label>
        <button onClick={search} disabled={busy !== "" || q.trim().length < 2}>{busy === "search" ? "Searching…" : "Search"}</button>
      </div>

      <DataTable caption="Document list" rows={rows} rowKey={(d) => d.id} columns={columns}
        empty={<Empty title="No documents yet" hint="Upload a PDF, DOCX, XLSX or CSV to begin." />} />

      {hits.length > 0 ? (
        <>
          <h2 style={{ marginTop: 20 }}>Search results for “{q}”</h2>
          <DataTable caption={`Search results for ${q}`} rows={hits} rowKey={(h) => `${h.documentId}-${h.chunkNo}`}
            columns={[
              { key: "doc", header: "Document", render: (h) => <span className="mono">{h.documentId.slice(0, 8)}</span> },
              { key: "chunk", header: "Chunk", numeric: true, render: (h) => h.chunkNo },
              { key: "ex", header: "Excerpt", render: (h) => h.excerpt },
            ]}
            empty={<Empty title="No matches" />} />
        </>
      ) : null}
    </Shell>
  );
}
