"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Shell from "../../components/Shell";
import { AuthScreen, Badge, ConfirmDialog, DataTable, Empty, EntityLink, ErrorBox, LiveRegion, Money, Pager, useBoot, type Column } from "../../components/ui";
import { api, fmtMinor, newIdemKey } from "../../lib/api";

type PO = { id: string; code: string; status: string; totalMinor: number; currency: string; supplierId: string; supplierName?: string };
type POLine = { id: string; lineNo: number; description: string; quantity: number; unitPriceMinor: number; lineTotalMinor: number };
type Invoice = { id: string; code: string; status: string };
type PODetail = { id: string; code: string; status: string; totalMinor: number; currency: string; supplierId: string; supplierName?: string; lines: POLine[]; invoices: Invoice[] };
type Supplier = { id: string; code: string; name: string };
type Requisition = { id: string; code: string; title: string; status: string };

/** Why a PO line was not evaluated, from `spend/price-evaluate`. */
const SKIP_REASON: Record<string, string> = {
  PRICE_CASE_OPEN: "already has an open case",
  PRICE_NO_HISTORY: "no approved invoice history for the supplier",
  PRICE_THIN_HISTORY: "too few like-for-like price points",
  PRICE_ITEM_INVALID: "item description too short to baseline",
  PRICE_BASELINE_INVALID: "baseline was not positive",
};

/** Server-enforced lifecycle. The UI mirrors it so it never offers an action the
 *  API will reject; the server stays the authority. */
const PO_ACTIONS: Record<string, { key: string; label: string; path?: string; confirm?: string }[]> = {
  draft: [{
    key: "approve",
    label: "Approve",
    path: "approve",
    // Approving is the point at which a purchase order commits money: it runs
    // the tier and segregation-of-duties checks, consumes the category budget
    // and is written to the audit chain against the approver. It was a single
    // unguarded click in a dense list, next to "Open".
    confirm: "Approving commits this purchase order against the category budget and records the decision in the audit chain under your name. It cannot be un-approved from this screen.",
  }],
  approved: [{
    key: "send",
    label: "Send to supplier",
    path: "send",
    confirm: "Sending issues this purchase order to the supplier. Treat it as an outbound commitment — the next step in the lifecycle is goods receipt.",
  }],
  // Receipt and invoicing need line quantities, so they are completed in the
  // detail panel rather than from the row. The row still names them so the next
  // step is legible from the list.
  sent: [{ key: "receipt", label: "Receive goods" }],
  received: [{ key: "invoice", label: "Record invoice" }],
  closed: [],
};

const TONE: Record<string, "ok" | "warn" | "bad" | "info" | undefined> = {
  approved: "info", sent: "info", received: "info", matched: "info", draft: "warn",
  closed: "ok", paid: "ok", rejected: "bad",
};

export function OrdersPage() {
  const [rows, setRows] = useState<PO[]>([]);
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [more, setMore] = useState(false);
  const [detail, setDetail] = useState<PODetail | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [requisitions, setRequisitions] = useState<Requisition[]>([]);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");

  const [form, setForm] = useState({ code: "", supplierId: "", requisitionId: "", currency: "INR", description: "", quantity: "1", unitPrice: "" });
  const [invoice, setInvoice] = useState({ code: "", quantity: "", unitPrice: "" });
  // Rejecting an invoice needs a written reason (the API refuses one without
  // it) and paying one needs a payment reference, so like the approvals queue
  // this is a per-row box that only appears while one of those is being typed.
  const [invRejecting, setInvRejecting] = useState("");
  const [invPaying, setInvPaying] = useState("");
  const [invReason, setInvReason] = useState("");
  /** The lifecycle action awaiting confirmation; null means no dialog. */
  const [pending, setPending] = useState<{ po: PO; key: string; label: string; path?: string; confirm?: string } | null>(null);
  /** The detail panel is rendered below a paginated table, so on a laptop it
   *  opened off-screen — "Open" looked like a button that did nothing. */
  const detailRef = useRef<HTMLElement>(null);
  const [scrollTo, setScrollTo] = useState("");
  useEffect(() => {
    if (!scrollTo || detail?.id !== scrollTo) return;
    detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    detailRef.current?.focus();
  }, [scrollTo, detail]);

  const load = useCallback(async (cur: string) => {
    // The PO page, the supplier picker and the requisition picker are three
    // independent reads — none depends on another's result — but this used to
    // `await` them one at a time. That cost was paid on every Pager click, not
    // just the first load, because the pickers are refreshed alongside the page
    // so a supplier or requisition created elsewhere shows up without a reload.
    const [r, s, req] = await Promise.all([
      api<PO[]>(`/api/v1/purchase-orders?limit=15&cursor=${encodeURIComponent(cur)}`),
      api<Supplier[]>("/api/v1/suppliers?limit=100&sort=name&order=asc"),
      // Only an approved requisition can answer a PO — see
      // `backend/app/routers/purchase.py::create_po` — so the picker only ever
      // offers ones that will actually convert, instead of a 422 after the fact.
      api<Requisition[]>("/api/v1/requisitions?status=approved&limit=100"),
    ]);
    setRows(r.data || []);
    setMore(!!r.pagination?.hasMore);
    setNextCursor(r.pagination?.nextCursor || "");
    setCursor(cur);
    setSuppliers(s.data || []);
    setRequisitions(req.data || []);
  }, []);

  const { state, error, reload } = useBoot(() => load(""));
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
          requisition_id: form.requisitionId,
          lines: [{ description: form.description, quantity: Number(form.quantity), unit_price_minor: Math.round(Number(form.unitPrice) * 100) }],
        }),
      });
      setNote(
        form.requisitionId
          ? `PO ${form.code.toUpperCase()} created as draft against the linked requisition, which is now ordered. The PO still needs approval.`
          : `PO ${form.code.toUpperCase()} created as draft. It now needs approval.`,
      );
      setForm({ ...form, code: "", requisitionId: "", description: "", quantity: "1", unitPrice: "" });
      await load("");
    });
  }

  /** Re-read the open PO after a mutation, without needing a list-shaped object. */
  async function refreshDetail() {
    if (!detail) return;
    const d = await api<PODetail>(`/api/v1/purchase-orders/${detail.id}`);
    setDetail(d.data);
  }

  async function open(po: PO, focus = true) {
    await act(`open-${po.id}`, async () => {
      const d = await api<PODetail>(`/api/v1/purchase-orders/${po.id}`);
      setDetail(d.data);
      setInvoice({ code: `INV-${po.code}`, quantity: String(d.data?.lines?.[0]?.quantity ?? 1), unitPrice: String((d.data?.lines?.[0]?.unitPriceMinor ?? 0) / 100) });
      if (focus) setScrollTo(po.id);
    });
  }

  async function poAction(po: PO, key: string, path?: string) {
    await act(`${key}-${po.id}`, async () => {
      await api(`/api/v1/purchase-orders/${po.id}/${path}`, { method: "POST", idemKey: newIdemKey() });
      setNote(`${po.code}: ${key} succeeded.`);
      await load(cursor);
      await open(po, false);
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
        const r = await api<{ opened: string[]; skipped: { line: number; reason: string }[] }>(
          `/api/v1/spend/price-evaluate/${detail.id}`, { method: "POST", idemKey: newIdemKey() },
        );
        const d = r.data;
        const opened = d?.opened?.length ?? 0;
        // Report the reasons the server actually gave. It used to claim
        // "no history" for every skipped line, which is wrong for a line that
        // already has an open case or simply has thin history.
        const reasons = Array.from(new Set((d?.skipped ?? []).map((s) => SKIP_REASON[s.reason] ?? s.reason)));
        setNote(
          opened > 0
            ? `${detail.code}: ${opened} price anomaly case(s) opened. Resolve under Spend.`
            : `${detail.code}: prices within baseline${reasons.length ? ` (${d?.skipped?.length} line(s) skipped: ${reasons.join(", ")})` : ""}.`,
        );
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

  async function rejectInvoice(inv: Invoice) {
    if (!detail) return;
    if (!invReason.trim()) { setErr("A rejection needs a written reason."); return; }
    await act(`inv-${inv.id}`, async () => {
      await api(`/api/v1/invoices/${inv.id}/reject`, {
        method: "POST", idemKey: newIdemKey(), body: JSON.stringify({ reason: invReason.trim() }),
      });
      setNote(`Invoice ${inv.code} rejected. The received quantity is released for re-billing.`);
      setInvRejecting(""); setInvReason("");
      await load(cursor);
      await refreshDetail();
    });
  }

  async function payInvoice(inv: Invoice) {
    if (!detail) return;
    if (!invReason.trim()) { setErr("Recording payment needs a reference."); return; }
    await act(`inv-${inv.id}`, async () => {
      await api(`/api/v1/invoices/${inv.id}/pay`, {
        method: "POST", idemKey: newIdemKey(), body: JSON.stringify({ reason: invReason.trim() }),
      });
      setNote(`Invoice ${inv.code} marked paid (ref. ${invReason.trim()}).`);
      setInvPaying(""); setInvReason("");
      await load(cursor);
      await refreshDetail();
    });
  }

  const columns: Column<PO>[] = [
    { key: "code", header: "Code", render: (p) => <span className="mono">{p.code}</span> },
    { key: "supplier", header: "Supplier", render: (p) => <EntityLink kind="supplier" id={p.supplierId} name={p.supplierName} /> },
    { key: "status", header: "Status", render: (p) => <Badge tone={TONE[p.status]}>{p.status}</Badge> },
    { key: "total", header: "Total", numeric: true, render: (p) => <Money>{fmtMinor(p.totalMinor, p.currency)}</Money> },
    {
      key: "act", header: "Actions", align: "end", render: (p) => (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <button className="ghost" onClick={() => open(p)} disabled={busy !== ""}>Open</button>
          {(PO_ACTIONS[p.status] || []).map((a) =>
            a.path ? (
              <button
                key={a.key}
                className="ghost"
                onClick={() => (a.confirm ? setPending({ po: p, ...a }) : poAction(p, a.key, a.path))}
                disabled={busy !== ""}
              >
                {busy === `${a.key}-${p.id}` ? "…" : a.label}
              </button>
            ) : (
              // A step that is completed in the detail panel. Rendering nothing
              // left the row silent about what happens next, on the one column
              // headed "Actions".
              <span key={a.key} className="next-step" title={`Open this order to ${a.label.toLowerCase()}`}>
                Next: {a.label.toLowerCase()}
              </span>
            ),
          )}
        </div>
      ),
    },
  ];

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Purchase orders</h1>
          <p>Raise an order, get it approved, receive the goods, then match the invoice before it is paid.</p>
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
          <label>Requisition
            <select aria-label="Linked requisition" value={form.requisitionId} onChange={(e) => setForm({ ...form, requisitionId: e.target.value })}>
              <option value="">None — raise directly</option>
              {requisitions.map((r) => <option key={r.id} value={r.id}>{r.code} — {r.title}</option>)}
            </select>
          </label>
          <label>Line<input aria-label="PO line description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="M10 hex bolt" /></label>
          <label>Qty<input aria-label="PO quantity" inputMode="numeric" size={5} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></label>
          <label>Unit price<input aria-label="PO unit price" inputMode="decimal" size={8} value={form.unitPrice} onChange={(e) => setForm({ ...form, unitPrice: e.target.value })} placeholder="12.50" /></label>
          <button onClick={createPo} disabled={busy !== "" || form.code.length < 2 || !form.supplierId || form.description.length < 2 || !form.unitPrice}>
            {busy === "create" ? "Creating…" : "Create PO"}
          </button>
        </div>
      </details>

      <DataTable caption="Purchase order list" rows={rows} rowKey={(p) => p.id} columns={columns}
        empty={<Empty title="No purchase orders yet" hint="A purchase order commits money to a supplier. Raise the first one under “New purchase order” above." />} />
      <Pager stack={stack} hasMore={more} busy={busy !== ""}
        onPrev={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv); }}
        onNext={async () => { setStack((s) => [...s, cursor]); await load(nextCursor); }} />

      {detail ? (
        <section className="panel detail-panel" style={{ marginTop: 24 }} ref={detailRef} tabIndex={-1} aria-label={`Purchase order ${detail.code}`}>
          <div className="detail-head">
            <h2 style={{ margin: 0 }}>{detail.code} <Badge tone={TONE[detail.status]}>{detail.status}</Badge></h2>
            <button className="ghost" onClick={() => { setDetail(null); setScrollTo(""); }}>Close</button>
          </div>
          <p style={{ color: "var(--muted)" }}>
            Supplier <EntityLink kind="supplier" id={detail.supplierId} name={detail.supplierName} /> · Total {fmtMinor(detail.totalMinor, detail.currency)}
          </p>

          <DataTable caption={`Lines for ${detail.code}`} rows={detail.lines} rowKey={(l) => l.id}
            columns={[
              { key: "no", header: "#", numeric: true, render: (l) => l.lineNo },
              { key: "desc", header: "Description", render: (l) => l.description },
              { key: "qty", header: "Qty", numeric: true, render: (l) => l.quantity },
              { key: "unit", header: "Unit", numeric: true, render: (l) => <Money>{fmtMinor(l.unitPriceMinor, detail.currency)}</Money> },
              { key: "total", header: "Line total", numeric: true, render: (l) => <Money>{fmtMinor(l.lineTotalMinor, detail.currency)}</Money> },
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
                key: "act", header: "Decision", render: (i) => {
                  const busyThis = busy === `inv-${i.id}`;
                  if (i.status === "received" || i.status === "matched") {
                    return (
                      <span className="toolbar" style={{ gap: 6 }}>
                        <button onClick={() => approveInvoice(i)} disabled={busy !== ""}>
                          {busyThis ? "Matching…" : "Approve"}
                        </button>
                        <button
                          className="ghost"
                          aria-pressed={invRejecting === i.id}
                          disabled={busy !== ""}
                          onClick={() => { setInvRejecting(invRejecting === i.id ? "" : i.id); setInvReason(""); }}
                        >
                          Reject
                        </button>
                        {invRejecting === i.id ? (
                          <span className="toolbar" style={{ gap: 6 }}>
                            <label className="sr-only" htmlFor={`inv-reason-${i.id}`}>Reason for rejection</label>
                            <input
                              id={`inv-reason-${i.id}`}
                              value={invReason}
                              onChange={(e) => setInvReason(e.target.value)}
                              placeholder="Why is this rejected?"
                              style={{ minWidth: 180 }}
                            />
                            <button onClick={() => rejectInvoice(i)} disabled={busy !== ""}>
                              {busyThis ? "…" : "Confirm"}
                            </button>
                          </span>
                        ) : null}
                      </span>
                    );
                  }
                  if (i.status === "approved") {
                    return (
                      <span className="toolbar" style={{ gap: 6 }}>
                        <button
                          className="ghost"
                          aria-pressed={invPaying === i.id}
                          disabled={busy !== ""}
                          onClick={() => { setInvPaying(invPaying === i.id ? "" : i.id); setInvReason(""); }}
                        >
                          Mark paid
                        </button>
                        {invPaying === i.id ? (
                          <span className="toolbar" style={{ gap: 6 }}>
                            <label className="sr-only" htmlFor={`inv-pay-${i.id}`}>Payment reference</label>
                            <input
                              id={`inv-pay-${i.id}`}
                              value={invReason}
                              onChange={(e) => setInvReason(e.target.value)}
                              placeholder="Payment reference"
                              style={{ minWidth: 180 }}
                            />
                            <button onClick={() => payInvoice(i)} disabled={busy !== ""}>
                              {busyThis ? "…" : "Confirm"}
                            </button>
                          </span>
                        ) : null}
                      </span>
                    );
                  }
                  return <span style={{ color: "var(--muted)" }}>{i.status === "paid" ? "settled" : "—"}</span>;
                },
              },
            ]}
            empty={<Empty title="No invoices" hint="Record one above once goods are received." />} />
        </section>
      ) : null}

      <ConfirmDialog
        open={!!pending}
        title={`${pending?.label ?? "Confirm"} ${pending?.po.code ?? "this order"}?`}
        confirmLabel={pending?.label ?? "Confirm"}
        busy={!!pending && busy === `${pending.key}-${pending.po.id}`}
        onCancel={() => setPending(null)}
        onConfirm={async () => {
          const p = pending;
          if (!p) return;
          setPending(null);
          await poAction(p.po, p.key, p.path);
        }}
        body={
          <>
            {pending ? (
              <>
                <strong className="mono">{pending.po.code}</strong> ·{" "}
                <strong className="mono">{fmtMinor(pending.po.totalMinor, pending.po.currency)}</strong>
                <br />
                <br />
              </>
            ) : null}
            {pending?.confirm}
          </>
        }
      />
    </Shell>
  );
}
