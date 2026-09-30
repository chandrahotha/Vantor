"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Shell from "../../components/Shell";
import { AuthScreen, Badge, ConfirmDialog, DataTable, Empty, ErrorBox, LiveRegion, Money, Pager, useBoot, type Column } from "../../components/ui";
import { api, fmtMinor, newIdemKey } from "../../lib/api";

type Contract = { id: string; code: string; title: string; status: string; endDate: string; valueMinor: number; currency: string };
type Obligation = { id: string; title: string; status: string; dueDate: string; owner: string };
type Supplier = { id: string; code: string; name: string };

const NEXT: Record<string, string[]> = {
  draft: ["review", "terminated"],
  review: ["active", "terminated"],
  active: ["expiring", "expired", "terminated"],
  expiring: ["renewed", "expired", "terminated"],
  renewed: [], expired: [], terminated: [],
};

/** What each transition does, in the user's words.
 *
 *  The buttons used to be labelled with the raw target status — a row offered
 *  "review", "terminated", "expired": adjectives, lower-case, with no verb and
 *  no object. Nothing on the row said whether "terminated" described the state
 *  the contract was in or the state the button would put it in, and two of the
 *  three are not reversible from this screen. */
const TRANSITION: Record<string, { label: string; confirm?: string; danger?: boolean }> = {
  review: { label: "Send for review" },
  active: { label: "Activate" },
  expiring: { label: "Flag as expiring" },
  renewed: { label: "Mark renewed" },
  expired: {
    danger: true,
    label: "Mark expired",
    confirm: "Marking this contract expired closes it for new purchase orders. There is no transition back to active from this screen.",
  },
  terminated: {
    danger: true,
    label: "Terminate",
    confirm: "Terminating ends this contract immediately and is a final state — it cannot be reopened, renewed or reactivated from this screen. The change is written to the audit chain against your name.",
  },
};

const TONE: Record<string, "ok" | "warn" | "bad" | "info" | undefined> = {
  active: "ok", expiring: "warn", expired: "bad", terminated: "bad", draft: "warn", review: "info", renewed: "info",
};

export default function ContractsPage() {
  const [rows, setRows] = useState<Contract[]>([]);
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [more, setMore] = useState(false);
  const [sel, setSel] = useState<(Contract & { obligations?: Obligation[] }) | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({ code: "", title: "", supplierId: "", value: "", currency: "INR", start: "", end: "" });
  const [obligationForm, setObligationForm] = useState({ title: "", due: "", owner: "" });
  /** The transition awaiting confirmation. Null means no dialog is open. */
  const [pending, setPending] = useState<{ contract: Contract; status: string } | null>(null);
  /** The detail panel renders below a paginated table, so on anything shorter
   *  than a tall desktop it opened off-screen: pressing "Open" looked like it
   *  had done nothing at all. */
  const detailRef = useRef<HTMLElement>(null);
  const [scrollTo, setScrollTo] = useState("");
  useEffect(() => {
    if (!scrollTo || sel?.id !== scrollTo) return;
    detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    detailRef.current?.focus();
  }, [scrollTo, sel]);

  const load = useCallback(async (cur: string) => {
    const [c, s] = await Promise.all([
      api<Contract[]>(`/api/v1/contracts?limit=15&cursor=${encodeURIComponent(cur)}`),
      api<Supplier[]>("/api/v1/suppliers?limit=100&sort=name&order=asc"),
    ]);
    setRows(c.data || []);
    setMore(!!c.pagination?.hasMore);
    setNextCursor(c.pagination?.nextCursor || "");
    setCursor(cur);
    setSuppliers(s.data || []);
  }, []);

  const { state, error, reload } = useBoot(() => load(""));
  const shownErr = err || error;

  async function act(key: string, fn: () => Promise<void>) {
    setBusy(key); setErr(""); setNote("");
    try { await fn(); } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(""); }
  }

  const createContract = () => act("create", async () => {
    await api("/api/v1/contracts", {
      method: "POST", idemKey: newIdemKey(),
      body: JSON.stringify({
        code: form.code, title: form.title, supplier_id: form.supplierId || "",
        value_minor: Math.round(Number(form.value || 0) * 100), currency: form.currency,
        start_date: form.start, end_date: form.end,
      }),
    });
    setNote(`Contract ${form.code.toUpperCase()} created.`);
    setForm({ code: "", title: "", supplierId: "", value: "", currency: "INR", start: "", end: "" });
    await load("");
  });

  const open = (c: Contract, focus = true) => act(`open-${c.id}`, async () => {
    const d = await api<Contract & { obligations?: Obligation[] }>(`/api/v1/contracts/${c.id}`);
    setSel(d.data);
    if (focus) setScrollTo(c.id);
  });

  const move = (c: Contract, status: string) => act(`status-${c.id}`, async () => {
    await api(`/api/v1/contracts/${c.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
    setNote(`${c.code} → ${status}`);
    await load(cursor);
    if (sel?.id === c.id) await open({ ...c, status }, false);
  });

  const sign = (c: Contract) => act(`sign-${c.id}`, async () => {
    await api(`/api/v1/contracts/${c.id}/sign`, { method: "POST", idemKey: newIdemKey(), body: JSON.stringify({ method: "internal" }) });
    setNote(`${c.code} signed (internal).`);
    await load(cursor);
  });

  const addObligation = () => act("obligation", async () => {
    if (!sel) return;
    await api(`/api/v1/contracts/${sel.id}/obligations`, {
      method: "POST", idemKey: newIdemKey(),
      body: JSON.stringify({ title: obligationForm.title, due_date: obligationForm.due, owner: obligationForm.owner, status: "open" }),
    });
    setNote(`Obligation "${obligationForm.title}" recorded.`);
    setObligationForm({ title: "", due: "", owner: "" });
    if (sel) await open(sel, false);
  });

  const columns: Column<Contract>[] = [
    { key: "code", header: "Code", render: (c) => <span className="mono">{c.code}</span> },
    { key: "title", header: "Title", render: (c) => c.title },
    { key: "status", header: "Status", render: (c) => <Badge tone={TONE[c.status]}>{c.status}</Badge> },
    { key: "end", header: "Ends", render: (c) => c.endDate || "—" },
    { key: "value", header: "Value", numeric: true, render: (c) => <Money>{fmtMinor(c.valueMinor, c.currency)}</Money> },
    {
      key: "act", header: "Actions", align: "end", render: (c) => (
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "flex-end" }}>
          <button className="ghost" onClick={() => open(c)} disabled={busy !== ""}>Open</button>
          {(NEXT[c.status] || []).map((s) => {
            const t = TRANSITION[s] ?? { label: s };
            return (
              <button
                key={s}
                className="ghost"
                onClick={() => (t.confirm ? setPending({ contract: c, status: s }) : move(c, s))}
                disabled={busy !== ""}
              >
                {busy === `status-${c.id}` ? "…" : t.label}
              </button>
            );
          })}
          {(c.status === "review" || c.status === "active" || c.status === "expiring") ? (
            <button onClick={() => sign(c)} disabled={busy !== ""}>
              {busy === `sign-${c.id}` ? "Signing…" : "Sign"}
            </button>
          ) : null}
        </div>
      ),
    },
  ];

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Contracts</h1>
          <p>Agreements in force, what each one obliges you to, and which are close to expiring.</p>
        </div>
      </div>

      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      <details className="panel">
        <summary>New contract</summary>
        <div className="toolbar">
          <label>Code<input aria-label="Contract code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="CT-2026-01" /></label>
          <label>Title<input aria-label="Contract title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Steel supply — FY27" /></label>
          <label>Supplier
            <select aria-label="Contract supplier" value={form.supplierId} onChange={(e) => setForm({ ...form, supplierId: e.target.value })}>
              <option value="">Internal (No external supplier)</option>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
            </select>
          </label>
          <label>Value<input aria-label="Contract value" inputMode="decimal" size={10} value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} placeholder="100000.00" /></label>
          <label>Currency<input aria-label="Currency" size={5} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></label>
          <label>Start<input aria-label="Start date" type="date" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></label>
          <label>End<input aria-label="End date" type="date" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} /></label>
          <button onClick={createContract} disabled={busy !== "" || form.code.length < 2 || form.title.length < 2}>
            {busy === "create" ? "Creating…" : "Create contract"}
          </button>
        </div>
      </details>

      <DataTable caption="Contract list" rows={rows} rowKey={(c) => c.id} columns={columns}
        empty={<Empty title="No contracts yet" hint="Create one above." />} />
      <Pager stack={stack} hasMore={more} busy={busy !== ""}
        onPrev={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv); }}
        onNext={async () => { setStack((s) => [...s, cursor]); await load(nextCursor); }} />

      {sel ? (
        <section className="panel detail-panel" style={{ marginTop: 24 }} ref={detailRef} tabIndex={-1} aria-label={`Contract ${sel.code}`}>
          <div className="detail-head">
            <h2 style={{ margin: 0 }}>{sel.code} <Badge tone={TONE[sel.status]}>{sel.status}</Badge></h2>
            <button className="ghost" onClick={() => { setSel(null); setScrollTo(""); }}>Close</button>
          </div>
          <p style={{ color: "var(--muted)", fontSize: 12 }}>
            Value {fmtMinor(sel.valueMinor, sel.currency)} · ends {sel.endDate || "—"}
          </p>

          <h3>Obligations</h3>
          <DataTable caption={`Obligations for ${sel.code}`} rows={sel.obligations || []} rowKey={(o) => o.id}
            columns={[
              { key: "title", header: "Obligation", render: (o) => o.title },
              { key: "owner", header: "Owner", render: (o) => o.owner || "—" },
              { key: "due", header: "Due", render: (o) => o.dueDate || "—" },
              { key: "status", header: "Status", render: (o) => <Badge tone={o.status === "met" ? "ok" : o.status === "breached" ? "bad" : "warn"}>{o.status}</Badge> },
            ]}
            empty={<Empty title="No obligations" hint="Add one below." />} />
          <div className="toolbar" style={{ marginTop: 10 }}>
            <label>Obligation<input aria-label="Obligation title" value={obligationForm.title} onChange={(e) => setObligationForm({ ...obligationForm, title: e.target.value })} placeholder="Quarterly penalty review" /></label>
            <label>Due<input aria-label="Obligation due date" type="date" value={obligationForm.due} onChange={(e) => setObligationForm({ ...obligationForm, due: e.target.value })} /></label>
            <label>Owner<input aria-label="Obligation owner" value={obligationForm.owner} onChange={(e) => setObligationForm({ ...obligationForm, owner: e.target.value })} placeholder="Procurement" /></label>
            <button onClick={addObligation} disabled={busy !== "" || obligationForm.title.length < 2}>
              {busy === "obligation" ? "Adding…" : "Add obligation"}
            </button>
          </div>
        </section>
      ) : null}

      <ConfirmDialog
        open={!!pending}
        title={`${TRANSITION[pending?.status ?? ""]?.label ?? "Change"} ${pending?.contract.code ?? "this contract"}?`}
        confirmLabel={TRANSITION[pending?.status ?? ""]?.label ?? "Confirm"}
        busy={busy.startsWith("status-")}
        tone={TRANSITION[pending?.status ?? ""]?.danger ? "danger" : "primary"}
        onCancel={() => setPending(null)}
        onConfirm={async () => {
          const p = pending;
          if (!p) return;
          setPending(null);
          await move(p.contract, p.status);
        }}
        body={<>{TRANSITION[pending?.status ?? ""]?.confirm}</>}
      />
    </Shell>
  );
}
