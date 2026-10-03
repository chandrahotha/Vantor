"use client";
import { useCallback, useState } from "react";
import Shell from "../../components/Shell";
import { AuthScreen, Badge, ConfirmDialog, DataTable, Empty, ErrorBox, LiveRegion, Money, Pager, StatCard, useBoot, type Column } from "../../components/ui";
import { API_URL, api, fmtMinor, newIdemKey } from "../../lib/api";
import { getSession } from "../../lib/auth";

type Doc = { id: string; filename: string; sizeBytes: number; status: string };
type Hit = { documentId: string; chunkNo: number; excerpt: string };

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
  /** Resolving a price case closes it for good — it leaves the open queue and
   *  the decision is audited — so both outcomes are stated before they happen
   *  rather than fired from a one-click button in a dense row. */
  const [pendingCase, setPendingCase] = useState<{ row: Case; status: "handed_off" | "dismissed" } | null>(null);

  const CASE_ACTION = {
    handed_off: {
      label: "Hand off to negotiation",
      body: "Hands this anomaly to the negotiation track and removes it from the open queue. The variance stays on record against the item.",
    },
    dismissed: {
      label: "Dismiss",
      body: "Dismissing records that the quoted price is acceptable despite the variance. The case leaves the open queue and will not be raised again for this line.",
    },
  } as const;

  const load = useCallback(async () => {
    // These three endpoints don't depend on one another, so they go in parallel
    // — this used to be three sequential `await`s, which made this page's load
    // time the *sum* of three round trips instead of the slowest one. `all`
    // (not `allSettled`) keeps the existing failure behaviour: any one request
    // failing still rejects the whole load and `useBoot` renders the error
    // screen, exactly as before.
    const [sp, intelRes, casesRes] = await Promise.all([
      api<Summary>("/api/v1/spend/summary"),
      api<Intel>("/api/v1/spend/intelligence"),
      api<Case[]>("/api/v1/spend/price-cases?status=open"),
    ]);
    setS(sp.data);
    setIntel(intelRes.data);
    setCases(casesRes.data || []);
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
      <div className="pagehead"><div><h1>Spend intelligence</h1><p>Where the money actually went, which suppliers you depend on, and where you are paying above baseline.</p></div></div>
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
              { key: "base", header: "Baseline", numeric: true, render: (p) => <Money>{fmtMinor(p.baselineMinor)}</Money> },
              { key: "quoted", header: "Quoted", numeric: true, render: (p) => <Money>{fmtMinor(p.quotedMinor)}</Money> },
              { key: "var", header: "Variance", numeric: true, render: (p) => `${p.varianceBp < 0 ? "−" : "+"}${(Math.abs(p.varianceBp) / 100).toFixed(1)}%` },
              {
                key: "act", header: "Resolve", align: "end", render: (p) => (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                    <button className="ghost" onClick={() => setPendingCase({ row: p, status: "handed_off" })} disabled={busy !== ""}>
                      {busy === `case-${p.id}` ? "…" : "Hand off"}
                    </button>
                    <button className="ghost" onClick={() => setPendingCase({ row: p, status: "dismissed" })} disabled={busy !== ""}>Dismiss</button>
                  </div>
                ),
              },
            ]}
            empty={<Empty title="No open price cases" hint="A case opens when a purchase order line is priced more than 10% away from its median baseline. Run “Price check” on an order to test its lines." />} />

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
              { key: "total", header: "Total", numeric: true, render: (r) => <Money>{fmtMinor(r.totalMinor, r.currency)}</Money> },
            ]}
            empty={<Empty title="Cube is empty" hint="Committed POs populate the cube." />} />
        </>
      )}

      <ConfirmDialog
        open={!!pendingCase}
        title={`${pendingCase ? CASE_ACTION[pendingCase.status].label : "Resolve"} this price case?`}
        confirmLabel={pendingCase ? CASE_ACTION[pendingCase.status].label : "Confirm"}
        tone={pendingCase?.status === "dismissed" ? "danger" : "primary"}
        busy={!!pendingCase && busy === `case-${pendingCase.row.id}`}
        onCancel={() => setPendingCase(null)}
        onConfirm={async () => {
          const p = pendingCase;
          if (!p) return;
          setPendingCase(null);
          await resolve(p.row.id, p.status);
        }}
        body={
          <>
            {pendingCase ? (
              <>
                <strong>{pendingCase.row.item}</strong> — baseline{" "}
                <span className="mono">{fmtMinor(pendingCase.row.baselineMinor)}</span>, quoted{" "}
                <span className="mono">{fmtMinor(pendingCase.row.quotedMinor)}</span>{" "}
                ({pendingCase.row.varianceBp < 0 ? "−" : "+"}
                {(Math.abs(pendingCase.row.varianceBp) / 100).toFixed(1)}%).
                <br />
                <br />
                {CASE_ACTION[pendingCase.status].body}
              </>
            ) : null}
          </>
        }
      />
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
  /** The term the currently displayed results belong to, or "" if no search has
   *  run. The results block used to be gated on `hits.length > 0`, so a search
   *  that matched nothing rendered nothing at all: the button appeared to do
   *  nothing, and the user could not tell a zero-result search from a failed
   *  one. */
  const [searched, setSearched] = useState("");

  // The list was a flat `limit=25` with no pager, so a tenant with more than 25
  // documents was shown a slice with nothing saying so — the 26th document
  // simply did not exist as far as this screen was concerned.
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [more, setMore] = useState(false);

  const load = useCallback(async (cur = "") => {
    const r = await api<Doc[]>(`/api/v1/documents?limit=25&cursor=${encodeURIComponent(cur)}`);
    setRows(r.data || []);
    setMore(!!r.pagination?.hasMore);
    setNextCursor(r.pagination?.nextCursor || "");
    setCursor(cur);
  }, []);

  const { state, error, reload } = useBoot(() => load(""));
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
        headers: { Authorization: `Bearer ${getSession()?.token ?? ""}`, "Idempotency-Key": newIdemKey() },
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
      await load("");
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
      await load(cursor);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Extraction failed");
    } finally {
      setBusy("");
    }
  }

  async function search() {
    const term = q.trim();
    if (term.length < 2) return;
    setBusy("search"); setErr("");
    try {
      const r = await api<Hit[]>(`/api/v1/documents/search?q=${encodeURIComponent(term)}`);
      setHits(r.data || []);
      setSearched(term);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Search failed");
      setHits([]);
      setSearched("");
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
      <div className="pagehead"><div><h1>Documents</h1><p>Upload a document, extract its text, then search across everything you have stored.</p></div></div>
      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      <div className="toolbar" role="search">
        <label>Upload<input type="file" aria-label="Upload document" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} /></label>
        <label>Search chunks<input aria-label="Search extracted text" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") search(); }} placeholder="at least 2 characters" /></label>
        <button onClick={search} disabled={busy !== "" || q.trim().length < 2}>{busy === "search" ? "Searching…" : "Search"}</button>
      </div>

      <DataTable caption="Document list" rows={rows} rowKey={(d) => d.id} columns={columns}
        empty={<Empty title="No documents yet" hint="Upload a PDF, DOCX, XLSX or CSV to begin." />} />
      <Pager stack={stack} hasMore={more} busy={busy !== ""}
        onPrev={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv); }}
        onNext={async () => { setStack((s) => [...s, cursor]); await load(nextCursor); }} />

      {searched ? (
        <>
          <div className="pagehead" style={{ marginTop: 24, marginBottom: 10 }}>
            <div>
              <h2 style={{ margin: 0 }}>
                Search results for “{searched}”{" "}
                <Badge tone={hits.length ? "info" : undefined}>{hits.length} match{hits.length === 1 ? "" : "es"}</Badge>
              </h2>
            </div>
            <div className="pagehead-actions">
              <button className="ghost" onClick={() => { setSearched(""); setHits([]); }}>Clear results</button>
            </div>
          </div>
          <DataTable caption={`Search results for ${searched}`} rows={hits} rowKey={(h) => `${h.documentId}-${h.chunkNo}`}
            columns={[
              { key: "doc", header: "Document", render: (h) => <span className="mono">{h.documentId.slice(0, 8)}</span> },
              { key: "chunk", header: "Chunk", numeric: true, render: (h) => h.chunkNo },
              { key: "ex", header: "Excerpt", render: (h) => h.excerpt },
            ]}
            empty={
              <Empty
                title={`Nothing matches “${searched}”`}
                hint="Search runs over extracted text only. A document has to be extracted before its contents are searchable — use “Extract text” on the row above."
              />
            } />
        </>
      ) : null}
    </Shell>
  );
}
