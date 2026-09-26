"use client";
import { useCallback, useState } from "react";
import Shell from "../../components/Shell";
import { AuthScreen, Badge, DataTable, Empty, ErrorBox, LiveRegion, Pager, useBoot, type Column } from "../../components/ui";
import { api, fmtMinor, newIdemKey } from "../../lib/api";

type PO = { id: string; code: string; status: string; totalMinor: number; currency: string; supplierId: string };
type POLine = { id: string; lineNo: number; description: string; quantity: number; unitPriceMinor: number; lineTotalMinor: number };
type Invoice = { id: string; code: string; status: string };
type PODetail = { id: string; code: string; status: string; totalMinor: number; currency: string; lines: POLine[]; invoices: Invoice[] };
type Supplier = { id: string; code: string; name: string };

/** Server-enforced lifecycle. The UI mirrors it so it never offers an action the
 *  API will reject; the server stays the authority. */
const PO_ACTIONS: Record<string, { key: string; label: string; path?: string; method?: string }[]> = {
  draft: [{ key: "approve", label: "Approve", path: "approve" }],
  approved: [{ key: "send", label: "Send to supplier", path: "send" }],
  sent: [{ key: "receipt", label: "Receive goods" }],
  received: [{ key: "invoice", label: "Record invoice" }],
  closed: [],
};

const TONE: Record<string, "ok" | "warn" | "bad" | "info" | undefined> = {
  approved: "info", sent: "info", received: "info", draft: "warn", closed: "ok", rejected: "bad",
};

export function OrdersPage() {
  const [rows, setRows] = useState<PO[]>([]);
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [more, setMore] = useState(false);
  const [detail, setDetail] = useState<PODetail | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");

  const [form, setForm] = useState({ code: "", supplierId: "", currency: "INR", description: "", quantity: "1", unitPrice: "" });
  const [invoice, setInvoice] = useState({ code: "", quantity: "", unitPrice: "" });

  const load = useCallback(async (cur: string) => {
    const r = await api<PO[]>(`/api/v1/purchase-orders?limit=15&cursor=${encodeURIComponent(cur)}`);
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

  async function createPo() {
    await act("create", async () => {
      await api("/api/v1/purchase-orders", {
        method: "POST", idemKey: newIdemKey(),
        body: JSON.stringify({
          code: form.code, supplier_id: form.supplierId, currency: form.currency,
          lines: [{ description: form.description, quantity: Number(form.quantity), unit_price_minor: Math.round(Number(form.unitPrice) * 100) }],
        }),
      });
      setNote(`PO ${form.code.toUpperCase()} created as draft. It now needs approval.`);
      setForm({ ...form, code: "", description: "", quantity: "1", unitPrice: "" });
      await load("");
    });
  }

  /** Re-read the open PO after a mutation, without needing a list-shaped object. */
  async function refreshDetail() {
    if (!detail) return;
    const d = await api<PODetail>(`/api/v1/purchase-orders/${detail.id}`);
    setDetail(d.data);
  }

  async function open(po: PO) {
    await act(`open-${po.id}`, async () => {
      const d = await api<PODetail>(`/api/v1/purchase-orders/${po.id}`);
      setDetail(d.data);
      setInvoice({ code: `INV-${po.code}`, quantity: String(d.data?.lines?.[0]?.quantity ?? 1), unitPrice: String((d.data?.lines?.[0]?.unitPriceMinor ?? 0) / 100) });
    });
  }

  async function poAction(po: PO, key: string, path?: string) {
    await act(`${key}-${po.id}`, async () => {
      await api(`/api/v1/purchase-orders/${po.id}/${path}`, { method: "POST", idemKey: newIdemKey() });
      setNote(`${po.code}: ${key} succeeded.`);
      await load(cursor);
      await open(po);
    });
  }

  async function receiveGoods() {
    if (!detail) return;
    await act("receipt", async () => {
      // Full-quantity receipt; partial receipts are supported by sending fewer units.
      await api(`/api/v1/purchase-orders/${detail.id}/receipts`, {
        method: "POST", idemKey: newIdemKey(),
        body: JSON.stringify({ notes: "Received via web", lines: detail.lines.map((l) => ({ po_line_id: l.id, quantity: l.quantity })) }),
      });
      setNote(`${detail.code}: goods received. An invoice can now be recorded.`);
      await load(cursor);
      await refreshDetail();
    });
  }

  async function createInvoice() {
    if (!detail) return;
    await act("invoice", async () => {
      await api(`/api/v1/purchase-orders/${detail.id}/invoices`, {
        method: "POST", idemKey: newIdemKey(),
        body: JSON.stringify({
          code: invoice.code, currency: detail.currency,
          lines: detail.lines.map((l) => ({ po_line_id: l.id, quantity: Number(invoice.quantity), unit_price_minor: Math.round(Number(invoice.unitPrice) * 100) })),
        }),
      });
      setNote(`${detail.code}: invoice ${invoice.code} recorded, pending 3-way match.`);
      await load(cursor);
      await refreshDetail();
    });
  }

  async function evaluatePrice() {
    if (!detail) return;
    await act("price", async () => {
      const r = await api<{ opened: string[]; skipped: { line: string; reason: string }[]; evaluated?: number }>(
        `/api/v1/spend/price-evaluate/${detail.id}`, { method: "POST", idemKey: newIdemKey() },
      );
      const d = r.data;
      setNote(d && (d.opened?.length ?? 0) > 0
        ? `${detail.code}: ${d.opened.length} price anomaly case(s) opened. Resolve under Spend.`
        : `${detail.code}: prices within baseline${d?.skipped?.length ? ` (${d.skipped.length} line(s) skipped: no history)` : ""}.`);
    });
  }

  async function approveInvoice(inv: Invoice) {
    if (!detail) return;
    await act(`inv-${inv.id}`, async () => {
      await api(`/api/v1/invoices/${inv.id}/approve`, { method: "POST", idemKey: newIdemKey() });
      setNote(`Invoice ${inv.code} approved after 3-way match. Actual spend posted to the ledger.`);
      await load(cursor);
      await refreshDetail();
    });
  }

  const columns: Column<PO>[] = [
    { key: "code", header: "Code", render: (p) => <span className="mono">{p.code}</span> },
    { key: "status", header: "Status", render: (p) => <Badge tone={TONE[p.status]}>{p.status}</Badge> },
    { key: "total", header: "Total", numeric: true, render: (p) => fmtMinor(p.totalMinor, p.currency) },
    {
      key: "act", header: "Actions", render: (p) => (
        <>
          <button className="ghost" onClick={() => open(p)} disabled={busy !== ""}>Open</button>{" "}
          {(PO_ACTIONS[p.status] || []).map((a) =>
            a.path ? (
              <button key={a.key} className="ghost" onClick={() => poAction(p, a.key, a.path)} disabled={busy !== ""}>
                {busy === `${a.key}-${p.id}` ? "…" : a.label}
              </button>
            ) : null,
          )}
        </>
      ),
    },
  ];

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Purchase orders</h1>
          <p>Requisition to invoice with tiered approvals, segregation of duties, budget gates and a server-side 3-way match.</p>
        </div>
      </div>

      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      <details className="panel">
        <summary>New purchase order</summary>
        <div className="toolbar">
          <label>Code<input aria-label="PO code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="PO-2026-01" /></label>
          <label>Supplier
            <select aria-label="PO supplier" value={form.supplierId} onChange={(e) => setForm({ ...form, supplierId: e.target.value })}>
              <option value="">Select…</option>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
            </select>
          </label>
          <label>Currency<input aria-label="PO currency" size={5} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></label>
          <label>Line<input aria-label="PO line description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="M10 hex bolt" /></label>
          <label>Qty<input aria-label="PO quantity" inputMode="numeric" size={5} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></label>
          <label>Unit price<input aria-label="PO unit price" inputMode="decimal" size={8} value={form.unitPrice} onChange={(e) => setForm({ ...form, unitPrice: e.target.value })} placeholder="12.50" /></label>
          <button onClick={createPo} disabled={busy !== "" || form.code.length < 2 || !form.supplierId || form.description.length < 2 || !form.unitPrice}>
            {busy === "create" ? "Creating…" : "Create PO"}
          </button>
        </div>
      </details>

      {state !== "ok" ? <AuthScreen state={state} error={error} />
        : (
        <>
          <DataTable caption="Purchase order list" rows={rows} rowKey={(p) => p.id} columns={columns}
            empty={<Empty title="No purchase orders yet" hint="Create one above, or via POST /api/v1/purchase-orders." />} />
          <Pager stack={stack} hasMore={more} busy={busy !== ""}
            onPrev={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv); }}
            onNext={async () => { setStack((s) => [...s, cursor]); await load(nextCursor); }} />
        </>
      )}

      {detail ? (
        <section className="panel" style={{ marginTop: 24 }}>
          <h2 style={{ marginTop: 0 }}>{detail.code} <Badge tone={TONE[detail.status]}>{detail.status}</Badge></h2>
          <p style={{ color: "var(--muted)" }}>Total {fmtMinor(detail.totalMinor, detail.currency)}</p>

          <DataTable caption={`Lines for ${detail.code}`} rows={detail.lines} rowKey={(l) => l.id}
            columns={[
              { key: "no", header: "#", numeric: true, render: (l) => l.lineNo },
              { key: "desc", header: "Description", render: (l) => l.description },
              { key: "qty", header: "Qty", numeric: true, render: (l) => l.quantity },
              { key: "unit", header: "Unit", numeric: true, render: (l) => fmtMinor(l.unitPriceMinor, detail.currency) },
              { key: "total", header: "Line total", numeric: true, render: (l) => fmtMinor(l.lineTotalMinor, detail.currency) },
            ]}
            empty={<Empty title="No lines" />} />

          {detail.status === "sent" ? (
            <button style={{ marginTop: 12 }} onClick={receiveGoods} disabled={busy !== ""}>
              {busy === "receipt" ? "Receiving…" : "Receive all goods"}
            </button>
          ) : null}

          {detail.status === "received" ? (
            <div className="toolbar" style={{ marginTop: 12 }}>
              <label>Invoice code<input aria-label="Invoice code" value={invoice.code} onChange={(e) => setInvoice({ ...invoice, code: e.target.value })} /></label>
              <label>Qty<input aria-label="Invoice quantity" inputMode="numeric" size={5} value={invoice.quantity} onChange={(e) => setInvoice({ ...invoice, quantity: e.target.value })} /></label>
              <label>Unit price<input aria-label="Invoice unit price" inputMode="decimal" size={8} value={invoice.unitPrice} onChange={(e) => setInvoice({ ...invoice, unitPrice: e.target.value })} /></label>
              <button onClick={createInvoice} disabled={busy !== "" || invoice.code.length < 2 || !invoice.quantity || !invoice.unitPrice}>
                {busy === "invoice" ? "Recording…" : "Record invoice"}
              </button>
            </div>
          ) : null}

          <div className="toolbar" style={{ marginTop: 14 }}>
            <button className="ghost" onClick={evaluatePrice} disabled={busy !== ""}>
              {busy === "price" ? "Checking…" : "Price check"}
            </button>
            <span style={{ color: "var(--faint)", fontSize: 12 }}>
              Compares every line to its median baseline; at 10%+ variance it opens a
              case under Spend — anomalies are resolved there, never silently.
            </span>
          </div>

          <h3>Invoices</h3>
          <DataTable caption={`Invoices for ${detail.code}`} rows={detail.invoices} rowKey={(i) => i.id}
            columns={[
              { key: "code", header: "Code", render: (i) => <span className="mono">{i.code}</span> },
              { key: "status", header: "Status", render: (i) => <Badge tone={TONE[i.status]}>{i.status}</Badge> },
              {
                key: "act", header: "3-way match", render: (i) =>
                  i.status === "received" ? (
                    <button onClick={() => approveInvoice(i)} disabled={busy !== ""}>
                      {busy === `inv-${i.id}` ? "Matching…" : "Approve"}
                    </button>
                  ) : <span style={{ color: "var(--muted)" }}>{i.status === "approved" ? "matched" : "—"}</span>,
              },
            ]}
            empty={<Empty title="No invoices" hint="Record one above once goods are received." />} />
        </section>
      ) : null}
    </Shell>
  );
}
