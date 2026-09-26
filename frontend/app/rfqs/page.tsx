"use client";
import { useCallback, useState } from "react";
import Shell from "../../components/Shell";
import { Badge, DataTable, Empty, ErrorBox, LiveRegion, Pager, Skeleton, useBoot, type Column } from "../../components/ui";
import { api, fmtMinor, newIdemKey } from "../../lib/api";

type Rfq = { id: string; code: string; title: string; status: string; currency: string; lineCount?: number };
type Comp = { quoteId: string; supplierId: string; supplierName: string; status: string; currency: string; totalMinor: number; lineCount: number };
type Supplier = { id: string; code: string; name: string };
type RfqLine = { id: string; lineNo: number; description: string; quantity: number; uom: string };

/** Legal status transitions, mirrored from the server so the UI never offers
 *  an action the API will reject. The server remains the authority. */
const NEXT_STATUS: Record<string, string[]> = {
  draft: ["sent"],
  sent: ["response"],
  response: ["evaluated"],
  evaluated: ["awarded"],
  awarded: [],
  closed: [],
};

const STATUS_TONE: Record<string, "ok" | "warn" | "bad" | "info" | undefined> = {
  awarded: "ok", evaluated: "info", sent: "info", response: "info", draft: "warn", closed: "bad",
};

export default function Rfqs() {
  const [rows, setRows] = useState<Rfq[]>([]);
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [more, setMore] = useState(false);
  const [sel, setSel] = useState<{ rfq: Rfq; comp: Comp[]; lines: RfqLine[]; currency: string } | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");

  // --- create form -----------------------------------------------------------
  const [form, setForm] = useState({ code: "", title: "", currency: "INR", description: "", quantity: "1", uom: "each" });

  // --- quote form ------------------------------------------------------------
  const [quote, setQuote] = useState({ supplierId: "", unitPrice: "", quantity: "" });

  const load = useCallback(async (cur: string) => {
    const r = await api<Rfq[]>(`/api/v1/rfqs?limit=15&cursor=${encodeURIComponent(cur)}`);
    setRows(r.data || []);
    setMore(!!r.pagination?.hasMore);
    setNextCursor(r.pagination?.nextCursor || "");
    setCursor(cur);
    const s = await api<Supplier[]>("/api/v1/suppliers?limit=100&sort=name&order=asc");
    setSuppliers(s.data || []);
  }, []);

  const { state, error } = useBoot(() => load(""));
  const shownErr = err || error;

  async function act(key: string, fn: () => Promise<void>) {
    setBusy(key); setErr(""); setNote("");
    try { await fn(); } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(""); }
  }

  async function createRfq() {
    await act("create", async () => {
      await api("/api/v1/rfqs", {
        method: "POST",
        idemKey: newIdemKey(),
        body: JSON.stringify({
          code: form.code, title: form.title, currency: form.currency,
          lines: [{ description: form.description, quantity: Number(form.quantity), uom: form.uom }],
        }),
      });
      setForm({ code: "", title: "", currency: form.currency, description: "", quantity: "1", uom: "each" });
      setNote(`RFQ ${form.code.toUpperCase()} created.`);
      await load("");
    });
  }

  async function open(r: Rfq) {
    await act(`open-${r.id}`, async () => {
      const [c, d] = await Promise.all([
        api<Comp[]>(`/api/v1/rfqs/${r.id}/comparison`),
        api<Rfq & { lines: RfqLine[] }>(`/api/v1/rfqs/${r.id}`),
      ]);
      setSel({ rfq: r, comp: c.data || [], lines: d.data?.lines || [], currency: d.data?.currency || r.currency || "" });
      setQuote({ supplierId: "", unitPrice: "", quantity: String(d.data?.lines?.[0]?.quantity ?? 1) });
    });
  }

  async function move(r: Rfq, status: string) {
    await act(`status-${r.id}`, async () => {
      await api(`/api/v1/rfqs/${r.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      setNote(`${r.code} → ${status}`);
      await load(cursor);
      if (sel?.rfq.id === r.id) await open({ ...r, status });
    });
  }

  async function submitQuote() {
    if (!sel) return;
    await act("quote", async () => {
      await api(`/api/v1/rfqs/${sel.rfq.id}/quotes`, {
        method: "POST",
        idemKey: newIdemKey(),
        body: JSON.stringify({
          supplier_id: quote.supplierId,
          currency: sel.currency,
          lines: [{ unit_price_minor: Math.round(Number(quote.unitPrice) * 100), quantity: Number(quote.quantity) }],
        }),
      });
      setNote(`Quote recorded for ${sel.rfq.code}.`);
      setQuote((q) => ({ ...q, unitPrice: "" }));
      await open(sel.rfq);
    });
  }

  async function award(quoteId: string) {
    if (!sel) return;
    await act(`award-${quoteId}`, async () => {
      await api(`/api/v1/rfqs/${sel.rfq.id}/award`, {
        method: "POST",
        idemKey: newIdemKey(),
        body: JSON.stringify({ quote_id: quoteId, reason: "Awarded from RFQ comparison" }),
      });
      setNote(`${sel.rfq.code} awarded. Savings booked to the ledger.`);
      await load(cursor);
      await open(sel.rfq);
    });
  }

  const columns: Column<Rfq>[] = [
    { key: "code", header: "Code", render: (r) => <span className="mono">{r.code}</span> },
    { key: "title", header: "Title", render: (r) => r.title },
    { key: "status", header: "Status", render: (r) => <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge> },
    {
      key: "actions", header: "Actions", render: (r) => (
        <>
          <button className="ghost" onClick={() => open(r)} disabled={busy !== ""}>Open</button>{" "}
          {NEXT_STATUS[r.status]?.map((s) => (
            <button key={s} className="ghost" onClick={() => move(r, s)} disabled={busy !== ""}>{s}</button>
          ))}
        </>
      ),
    },
  ];

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>RFQs</h1>
          <p>Create, publish, collect quotes, compare and award. Totals are server-computed — the browser never sends a total.</p>
        </div>
      </div>

      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      <details className="panel">
        <summary>New RFQ</summary>
        <div className="toolbar">
          <label>Code<input aria-label="RFQ code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="RFQ-2026-01" /></label>
          <label>Title<input aria-label="RFQ title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Steel fasteners" /></label>
          <label>Currency<input aria-label="Currency" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} size={5} /></label>
          <label>Line<input aria-label="Line description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="M10 hex bolt" /></label>
          <label>Qty<input aria-label="Quantity" inputMode="numeric" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} size={5} /></label>
          <label>UoM<input aria-label="Unit of measure" value={form.uom} onChange={(e) => setForm({ ...form, uom: e.target.value })} size={6} /></label>
          <button onClick={createRfq} disabled={busy !== "" || form.code.length < 2 || form.title.length < 2 || form.description.length < 2}>
            {busy === "create" ? "Creating…" : "Create RFQ"}
          </button>
        </div>
      </details>

      {state === "loading" ? <Skeleton rows={4} label="Loading RFQs" />
        : state === "signin" ? <Empty title="Sign-in required" hint="Your session is not authenticated against the Vantor realm." />
        : (
        <>
          <DataTable
            caption="RFQ list"
            rows={rows}
            rowKey={(r) => r.id}
            columns={columns}
            empty={<Empty title="No RFQs yet" hint="Create one above, or via POST /api/v1/rfqs." />}
          />
          <Pager
            stack={stack}
            hasMore={more}
            busy={busy !== ""}
            onPrev={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv); }}
            onNext={async () => { setStack((s) => [...s, cursor]); await load(nextCursor); }}
          />
        </>
      )}

      {sel ? (
        <section className="panel" style={{ marginTop: 24 }}>
          <h2 style={{ marginTop: 0 }}>{sel.rfq.code} — {sel.rfq.title}</h2>

          <h3>Lines</h3>
          <DataTable
            caption={`Lines for ${sel.rfq.code}`}
            rows={sel.lines}
            rowKey={(l) => l.id}
            columns={[
              { key: "no", header: "#", numeric: true, render: (l) => l.lineNo },
              { key: "desc", header: "Description", render: (l) => l.description },
              { key: "qty", header: "Qty", numeric: true, render: (l) => l.quantity },
              { key: "uom", header: "UoM", render: (l) => l.uom },
            ]}
            empty={<Empty title="No lines" />}
          />

          <h3>Comparison</h3>
          <DataTable
            caption={`Quote comparison for ${sel.rfq.code}`}
            rows={sel.comp}
            rowKey={(q) => q.quoteId}
            columns={[
              { key: "sup", header: "Supplier", render: (q) => q.supplierName },
              { key: "status", header: "Status", render: (q) => <Badge tone={q.status === "awarded" ? "ok" : undefined}>{q.status}</Badge> },
              { key: "lines", header: "Lines", numeric: true, render: (q) => q.lineCount },
              { key: "total", header: "Total", numeric: true, render: (q) => fmtMinor(q.totalMinor, q.currency || sel.currency) },
              {
                key: "act", header: "Award", render: (q) =>
                  sel.rfq.status === "evaluated" && q.status !== "awarded" && q.status !== "rejected" ? (
                    <button onClick={() => award(q.quoteId)} disabled={busy !== ""}>
                      {busy === `award-${q.quoteId}` ? "Awarding…" : "Award"}
                    </button>
                  ) : <span style={{ color: "var(--muted)" }}>—</span>,
              },
            ]}
            empty={<Empty title="No quotes yet" hint="Record a quote below, or via POST /api/v1/rfqs/{id}/quotes." />}
          />

          {sel.rfq.status !== "awarded" ? (
            <div className="toolbar" style={{ marginTop: 12 }}>
              <label>Supplier
                <select aria-label="Quote supplier" value={quote.supplierId} onChange={(e) => setQuote({ ...quote, supplierId: e.target.value })}>
                  <option value="">Select…</option>
                  {suppliers.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
                </select>
              </label>
              <label>Unit price ({sel.currency || "ccy"})
                <input aria-label="Unit price" inputMode="decimal" value={quote.unitPrice} onChange={(e) => setQuote({ ...quote, unitPrice: e.target.value })} placeholder="12.50" size={8} />
              </label>
              <label>Qty
                <input aria-label="Quote quantity" inputMode="numeric" value={quote.quantity} onChange={(e) => setQuote({ ...quote, quantity: e.target.value })} size={5} />
              </label>
              <button onClick={submitQuote} disabled={busy !== "" || !quote.supplierId || !quote.unitPrice || !quote.quantity}>
                {busy === "quote" ? "Recording…" : "Record quote"}
              </button>
            </div>
          ) : null}
        </section>
      ) : null}
    </Shell>
  );
}
