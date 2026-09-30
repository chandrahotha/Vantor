"use client";
import { useCallback, useState } from "react";
import Shell from "../../components/Shell";
import { AuthScreen, Badge, DataTable, Empty, ErrorBox, LiveRegion, Pager, useBoot, type Column } from "../../components/ui";
import { api, newIdemKey } from "../../lib/api";

type Req = { id: string; code: string; title: string; status: string; requester: string; createdAt: string };

export default function Requisitions() {
  const [rows, setRows] = useState<Req[]>([]);
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [more, setMore] = useState(false);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({ code: "", title: "", description: "", quantity: "1", estPrice: "" });

  const load = useCallback(async (cur: string) => {
    const r = await api<Req[]>(`/api/v1/requisitions?limit=15&cursor=${encodeURIComponent(cur)}`);
    setRows(r.data || []);
    setMore(!!r.pagination?.hasMore);
    setNextCursor(r.pagination?.nextCursor || "");
    setCursor(cur);
  }, []);

  const { state, error, reload } = useBoot(() => load(""));
  const shownErr = err || error;

  async function create() {
    setBusy("create"); setErr(""); setNote("");
    try {
      await api("/api/v1/requisitions", {
        method: "POST", idemKey: newIdemKey(),
        body: JSON.stringify({
          code: form.code, title: form.title,
          lines: [{ description: form.description, quantity: Number(form.quantity), est_price_minor: Math.round(Number(form.estPrice || 0) * 100) }],
        }),
      });
      setNote(`Requisition ${form.code.toUpperCase()} created as draft.`);
      setForm({ code: "", title: "", description: "", quantity: "1", estPrice: "" });
      await load("");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy("");
    }
  }

  async function submit(r: Req) {
    setBusy(r.id); setErr(""); setNote("");
    try {
      await api(`/api/v1/requisitions/${r.id}/submit`, { method: "POST", idemKey: newIdemKey() });
      setNote(`${r.code} submitted — approval tiers seeded automatically.`);
      await load(cursor);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setBusy("");
    }
  }

  const columns: Column<Req>[] = [
    { key: "code", header: "Code", render: (r) => <span className="mono">{r.code}</span> },
    { key: "title", header: "Title", render: (r) => r.title },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.status === "submitted" ? "info" : r.status === "approved" ? "ok" : "warn"}>{r.status}</Badge> },
    { key: "requester", header: "Requester", render: (r) => <span className="mono" style={{ fontSize: 12 }}>{r.requester}</span> },
    {
      key: "act", header: "", render: (r) =>
        r.status === "draft" ? (
          <button onClick={() => submit(r)} disabled={busy !== ""}>{busy === r.id ? "…" : "Submit"}</button>
        ) : <span style={{ color: "var(--faint)", fontSize: 12 }}>{r.status}</span>,
    },
  ];

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Requisitions</h1>
          <p>Ask for something before it is bought. Submitting a requisition starts the approval chain.</p>
        </div>
      </div>

      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      <details className="panel">
        <summary>New requisition</summary>
        <div className="toolbar">
          <label>Code<input aria-label="Requisition code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="REQ-101" /></label>
          <label>Title<input aria-label="Requisition title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Fasteners topup" /></label>
          <label>Line<input aria-label="Line description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="M10 hex bolt" /></label>
          <label>Qty<input aria-label="Quantity" inputMode="numeric" size={5} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></label>
          <label>Est. unit price<input aria-label="Estimated unit price" inputMode="decimal" size={9} value={form.estPrice} onChange={(e) => setForm({ ...form, estPrice: e.target.value })} placeholder="5.00" /></label>
          <button onClick={create} disabled={busy !== "" || form.code.length < 2 || form.title.length < 2 || form.description.length < 2}>
            {busy === "create" ? "Creating…" : "Create requisition"}
          </button>
        </div>
      </details>

      <DataTable caption="Requisitions" rows={rows} rowKey={(r) => r.id} columns={columns}
        empty={<Empty title="No requisitions yet" hint="Create one above." />} />
      <Pager stack={stack} hasMore={more} busy={busy !== ""}
        onPrev={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv); }}
        onNext={async () => { setStack((s) => [...s, cursor]); await load(nextCursor); }} />
    </Shell>
  );
}
