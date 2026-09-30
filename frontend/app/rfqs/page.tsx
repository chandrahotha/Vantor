"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Shell from "../../components/Shell";
import { AuthScreen, Badge, Button, ConfirmDialog, DataTable, Empty, ErrorBox, FilterBar, LiveRegion, Money, Pager, Segmented, useBoot, useToast, type Column } from "../../components/ui";
import { api, fmtMinor, newIdemKey } from "../../lib/api";

type Rfq = { id: string; code: string; title: string; status: string; currency: string; lineCount?: number };
type Comp = { quoteId: string; supplierId: string; supplierName: string; status: string; currency: string; totalMinor: number; lineCount: number };
type Supplier = { id: string; code: string; name: string };
type RfqLine = { id: string; lineNo: number; description: string; quantity: number; uom: string };
/** One explainable allocation from the optimizer, in the server's own shape. */
type Allocation = { supplier_id: string; quote_id: string; share_bp: number; cost_minor: number; reason: string };
type OptimizerResult = {
  allocations: Allocation[];
  total_minor: number;
  share_sum_bp: number;
  violations: string[];
};

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

/** The verb for each transition, and what the destination state means.
 *
 *  The row buttons were labelled with the raw target status — "sent",
 *  "response", "evaluated" — which reads as a description of the row rather
 *  than an instruction, and gives no hint that pressing it changes anything. */
const TRANSITION: Record<string, { label: string; hint: string }> = {
  sent: { label: "Issue to suppliers", hint: "opens the RFQ for quotes" },
  response: { label: "Open for responses", hint: "quotes can now be recorded" },
  evaluated: { label: "Mark evaluated", hint: "unlocks the Award action" },
  awarded: { label: "Close as awarded", hint: "locks the RFQ" },
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
  const [plan, setPlan] = useState<OptimizerResult | null>(null);
  const toast = useToast();
  /** The quote an award confirmation is open for. Null means no dialog. The
   *  previous behaviour awarded on a single click in a dense comparison table,
   *  which books real savings to the ledger — the Grade-5 "zero surprise
   *  mutations" rule requires the consequence be stated before it happens. */
  const [awardTarget, setAwardTarget] = useState<Comp | null>(null);
  // Server-side search and status filter. `/api/v1/rfqs` has accepted `search`
  // and `status` all along (backend/app/routers/sourcing.py:91) — they were
  // simply never exposed, so the page showed an unfilterable list. Both are
  // applied by the server, never by filtering the returned page in the browser,
  // which would present a partial list as if it were the whole tenant.
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  /** The comparison panel renders under a paginated list, so on a laptop it
   *  opened below the fold and "Open" looked inert. */
  const detailRef = useRef<HTMLElement>(null);
  const [scrollTo, setScrollTo] = useState("");
  useEffect(() => {
    if (!scrollTo || sel?.rfq.id !== scrollTo) return;
    detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    detailRef.current?.focus();
  }, [scrollTo, sel]);

  // --- create form -----------------------------------------------------------
  const [form, setForm] = useState({ code: "", title: "", currency: "INR", description: "", quantity: "1", uom: "each" });

  // --- quote form ------------------------------------------------------------
  const [quote, setQuote] = useState({ supplierId: "", unitPrice: "", quantity: "" });

  const load = useCallback(async (cur: string, search = "", status = "") => {
    const params = new URLSearchParams({ limit: "15", cursor: cur });
    if (search) params.set("search", search);
    if (status) params.set("status", status);
    const r = await api<Rfq[]>(`/api/v1/rfqs?${params.toString()}`);
    setRows(r.data || []);
    setMore(!!r.pagination?.hasMore);
    setNextCursor(r.pagination?.nextCursor || "");
    setCursor(cur);
    const s = await api<Supplier[]>("/api/v1/suppliers?limit=100&sort=name&order=asc");
    setSuppliers(s.data || []);
  }, []);

  const { state, error, reload } = useBoot(() => load(""));
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

  async function open(r: Rfq, focus = true) {
    await act(`open-${r.id}`, async () => {
      const [c, d] = await Promise.all([
        api<Comp[]>(`/api/v1/rfqs/${r.id}/comparison`),
        api<Rfq & { lines: RfqLine[] }>(`/api/v1/rfqs/${r.id}`),
      ]);
        setSel({ rfq: r, comp: c.data || [], lines: d.data?.lines || [], currency: d.data?.currency || r.currency || "" });
        setQuote({ supplierId: "", unitPrice: "", quantity: String(d.data?.lines?.[0]?.quantity ?? 1) });
        // Drop any previous proposal: a plan computed for another RFQ must never
        // be shown against this one.
        setPlan(null);
        if (focus) setScrollTo(r.id);
    });
  }

  async function move(r: Rfq, status: string) {
    await act(`status-${r.id}`, async () => {
      await api(`/api/v1/rfqs/${r.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      setNote(`${r.code} → ${status}`);
      await load(cursor, q, statusFilter);
      if (sel?.rfq.id === r.id) await open({ ...r, status }, false);
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
      await open(sel.rfq, false);
    });
  }

  async function optimize() {
    if (!sel) return;
    await act("optimize", async () => {
      // The server returns per-supplier reason, pro-rated cost, the share sum
      // and any cap violations. Only reading `.length` discarded all of it, so
      // a share-cap breach was invisible on a page that promises explainable
      // allocations.
      const r = await api<OptimizerResult>(
        `/api/v1/rfqs/${sel.rfq.id}/optimize`, { method: "POST", idemKey: newIdemKey(), body: "{}" },
      );
      setPlan(r.data);
      const allocs = r.data.allocations || [];
      const n = allocs.length;
      const v = r.data.violations?.length ?? 0;
      setNote(
        !n
          ? `No allocation proposed for ${sel.rfq.code}.`
          : v
            ? `Optimizer proposed a ${n}-way split for ${sel.rfq.code} with ${v} policy violation${v === 1 ? "" : "s"} — review before awarding.`
            : `Optimizer proposed a ${n}-way split for ${sel.rfq.code}. Award still requires the Award action.`,
      );
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
      toast("ok", `${sel.rfq.code} awarded — savings booked to the ledger.`);
      await load(cursor, q, statusFilter);
      await open(sel.rfq, false);
    });
  }

  const columns: Column<Rfq>[] = [
    { key: "code", header: "Code", render: (r) => <span className="mono">{r.code}</span> },
    { key: "title", header: "Title", render: (r) => r.title },
    { key: "status", header: "Status", render: (r) => <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge> },
    {
      key: "actions", header: "Actions", render: (r) => (
        <>
          <Button variant="ghost" size="sm" onClick={() => open(r)} disabled={busy !== ""}>Open</Button>{" "}
          {NEXT_STATUS[r.status]?.map((s) => (
            <Button
              key={s}
              variant="secondary"
              size="sm"
              title={TRANSITION[s]?.hint}
              loading={busy === `status-${r.id}`}
              onClick={() => move(r, s)}
              disabled={busy !== ""}
            >
              {TRANSITION[s]?.label ?? s}
            </Button>
          ))}
        </>
      ),
    },
  ];

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>RFQs</h1>
          <p>Ask several suppliers to quote the same lines, compare what comes back, and award the work.</p>
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
          <Button onClick={createRfq} loading={busy === "create"} disabled={busy !== "" || form.code.length < 2 || form.title.length < 2 || form.description.length < 2}>
            Create RFQ
          </Button>
        </div>
      </details>

      <FilterBar>
        <label>Search
          <input
            type="search"
            aria-label="Search RFQs"
            value={q}
            placeholder="Code or title"
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setStack([]);
                load("", q, statusFilter).catch((err: unknown) => setErr(String(err)));
              }
            }}
          />
        </label>
        <Button
          variant="secondary"
          onClick={() => {
            setStack([]);
            load("", q, statusFilter).catch((err: unknown) => setErr(String(err)));
          }}
        >
          Search
        </Button>
        <span className="spacer" />
        <Segmented
          label="Filter by status"
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v);
            setStack([]);
            load("", q, v).catch((err: unknown) => setErr(String(err)));
          }}
          options={[
            { value: "", label: "All" },
            { value: "draft", label: "Draft" },
            { value: "sent", label: "Sent" },
            { value: "response", label: "Response" },
            { value: "evaluated", label: "Evaluated" },
            { value: "awarded", label: "Awarded" },
          ]}
        />
      </FilterBar>

      <DataTable
        caption="RFQ list"
        rows={rows}
        rowKey={(r) => r.id}
        columns={columns}
        empty={<Empty
          title={q || statusFilter ? "No RFQs match these filters" : "No RFQs yet"}
          hint={q || statusFilter ? "Adjust or clear the filters above." : "An RFQ collects comparable quotes from several suppliers for the same lines. Start one under “New RFQ” above."}
        />}
      />
      <Pager
        stack={stack}
        hasMore={more}
        busy={busy !== ""}
        onPrev={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv, q, statusFilter); }}
        onNext={async () => { setStack((s) => [...s, cursor]); await load(nextCursor, q, statusFilter); }}
      />

      {sel ? (
        <section className="panel detail-panel" style={{ marginTop: 24 }} ref={detailRef} tabIndex={-1} aria-label={`RFQ ${sel.rfq.code}`}>
          <div className="detail-head">
            <h2 style={{ margin: 0 }}>{sel.rfq.code} — {sel.rfq.title} <Badge tone={STATUS_TONE[sel.rfq.status]}>{sel.rfq.status}</Badge></h2>
            <Button variant="ghost" size="sm" onClick={() => { setSel(null); setScrollTo(""); }}>Close</Button>
          </div>

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

          {sel.rfq.status === "evaluated" ? (
            <div className="toolbar" style={{ marginTop: 12 }}>
              <button className="ghost" onClick={optimize} disabled={busy !== ""}>
                {busy === "optimize" ? "Computing…" : "Suggest allocation"}
              </button>
              <span style={{ color: "var(--faint)", fontSize: 12 }}>
                Read-only. The optimizer proposes a share-capped split; a human still awards — never the model.
              </span>
            </div>
          ) : null}

          {plan && plan.allocations?.length ? (
            <>
              <h3>Suggested allocation</h3>
              {plan.violations?.length ? (
                <div className="error" role="alert">
                  <div>Share-cap violations — resolve these before awarding:</div>
                  <ul>{plan.violations.map((v, i) => <li key={i}>{v}</li>)}</ul>
                </div>
              ) : null}
              <DataTable
                caption={`Optimizer proposal for ${sel.rfq.code}`}
                rows={plan.allocations}
                rowKey={(a) => a.quote_id || a.supplier_id}
                columns={[
                  { key: "sup", header: "Supplier", render: (a) => a.supplier_id },
                  { key: "share", header: "Share", numeric: true, render: (a) => `${(a.share_bp / 100).toFixed(2)}%` },
                  { key: "bp", header: "bp", numeric: true, render: (a) => a.share_bp },
                  { key: "cost", header: "Cost", numeric: true, render: (a) => <Money>{fmtMinor(a.cost_minor, sel.currency)}</Money> },
                  { key: "why", header: "Why", render: (a) => a.reason },
                ]}
                empty={<Empty title="No allocation" />}
              />
              <p style={{ color: "var(--muted)", fontSize: 12 }}>
                <span className="mono">{fmtMinor(plan.total_minor, sel.currency)}</span> total · shares sum to{" "}
                <span className="mono">{plan.share_sum_bp}bp</span>
                {plan.share_sum_bp === 10000 ? " (fully allocated)" : " (not fully allocated — treat with care)"}
              </p>
            </>
          ) : null}

          <h3>Comparison</h3>
          <DataTable
            caption={`Quote comparison for ${sel.rfq.code}`}
            rows={sel.comp}
            rowKey={(q) => q.quoteId}
            columns={[
              { key: "sup", header: "Supplier", render: (q) => q.supplierName },
              { key: "status", header: "Status", render: (q) => <Badge tone={q.status === "awarded" ? "ok" : undefined}>{q.status}</Badge> },
              { key: "lines", header: "Lines", numeric: true, render: (q) => q.lineCount },
              { key: "total", header: "Total", numeric: true, render: (q) => <Money>{fmtMinor(q.totalMinor, q.currency || sel.currency)}</Money> },
              {
                key: "act", header: "Award", render: (q) =>
                  sel.rfq.status === "evaluated" && q.status !== "awarded" && q.status !== "rejected" ? (
                    <Button size="sm" onClick={() => setAwardTarget(q)} disabled={busy !== ""}>
                      Award
                    </Button>
                  ) : <span style={{ color: "var(--muted)" }}>—</span>,
              },
            ]}
            empty={<Empty title="No quotes yet" hint="Quotes returned by suppliers are recorded here so they can be compared side by side. Add the first one in the form below." />}
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
              <Button onClick={submitQuote} loading={busy === "quote"} disabled={busy !== "" || !quote.supplierId || !quote.unitPrice || !quote.quantity}>
                Record quote
              </Button>
            </div>
          ) : null}
        </section>
      ) : null}

      <ConfirmDialog
        open={!!awardTarget}
        title={`Award ${sel?.rfq.code ?? "this RFQ"}?`}
        confirmLabel="Award and book savings"
        busy={busy.startsWith("award-")}
        onCancel={() => setAwardTarget(null)}
        onConfirm={async () => {
          const target = awardTarget;
          if (!target) return;
          setAwardTarget(null);
          await award(target.quoteId);
        }}
        body={
          <>
            This awards <strong>{awardTarget?.supplierName}</strong> at{" "}
            <strong className="mono">
              {fmtMinor(awardTarget?.totalMinor ?? 0, awardTarget?.currency || sel?.currency)}
            </strong>{" "}
            across {awardTarget?.lineCount ?? 0} line{awardTarget?.lineCount === 1 ? "" : "s"}.
            <br />
            <br />
            Awarding books the savings to the ledger and locks this RFQ. It cannot be
            undone from this screen.
          </>
        }
      />
    </Shell>
  );
}
