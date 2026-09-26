"use client";
import { useCallback, useState } from "react";
import Shell from "../../components/Shell";
import { AuthScreen, Badge, DataTable, Empty, ErrorBox, LiveRegion, useBoot, type Column } from "../../components/ui";
import { api, newIdemKey } from "../../lib/api";

type IType = string;
type Integration = { id: string; name: string; itype: IType; status: string; createdAt: string };
type Delivery = { id: string; event: string; status: string; attempts: number };

const TONE: Record<string, "ok" | "warn" | "bad" | "info" | undefined> = {
  active: "ok", disabled: "warn", failed: "bad",
  delivered: "ok", failed_delivery: "bad", pending: "warn",
};

export default function Integrations() {
  const [types, setTypes] = useState<string[]>([]);
  const [rows, setRows] = useState<Integration[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({ name: "", itype: "erp", secret_ref: "" });
  const [whForm, setWhForm] = useState({ url: "", events: "" });

  const load = useCallback(async () => {
    const [t, i, d] = await Promise.all([
      api<{ types: string[] }>("/api/v1/integrations/types"),
      api<Integration[]>("/api/v1/integrations"),
      api<Delivery[]>("/api/v1/webhooks/deliveries?limit=25"),
    ]);
    setTypes(t.data?.types || []);
    setRows(i.data || []);
    setDeliveries(d.data || []);
  }, []);

  const { state, error } = useBoot(load);
  const shownErr = err || error;

  async function act(key: string, fn: () => Promise<void>) {
    setBusy(key); setErr(""); setNote("");
    try { await fn(); await load(); } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(""); }
  }

  const register = () => act("reg", async () => {
    await api("/api/v1/integrations", { method: "POST", idemKey: newIdemKey(), body: JSON.stringify(form) });
    setNote(`Integration ${form.name} registered (disabled — enable it in code).`);
    setForm({ name: "", itype: "erp", secret_ref: "" });
  });

  const addWebhook = () => act("wh", async () => {
    await api("/api/v1/webhooks/endpoints", {
      method: "POST", idemKey: newIdemKey(),
      body: JSON.stringify({ url: whForm.url, events: whForm.events ? whForm.events.split(",").map((s) => s.trim()) : [], secret_ref: "" }),
    });
    setNote("Webhook endpoint registered. Delivers only after a real event fires.");
    setWhForm({ url: "", events: "" });
  });

  const ping = () => act("ping", async () => {
    const r = await api<{ deliveries: number }>("/api/v1/webhooks/test", { method: "POST", idemKey: newIdemKey() });
    setNote(`Ping delivered to ${r.data.deliveries} endpoint(s).`);
  });

  const regCols: Column<Integration>[] = [
    { key: "name", header: "Name", render: (r) => r.name },
    { key: "type", header: "Type", render: (r) => <Badge tone="info">{r.itype}</Badge> },
    { key: "status", header: "Status", render: (r) => <Badge tone={TONE[r.status]}>{r.status}</Badge> },
  ];

  const delCols: Column<Delivery>[] = [
    { key: "event", header: "Event", render: (d) => d.event },
    { key: "status", header: "Status", render: (d) => <Badge tone={TONE[d.status]}>{d.status}</Badge> },
    { key: "attempts", header: "Attempts", numeric: true, render: (d) => d.attempts },
  ];

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Integrations</h1>
          <p>Adapters connectors and webhook endpoints. Secrets are vault-referenced; nothing raw is stored.</p>
        </div>
      </div>
      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      {state !== "ok" ? <AuthScreen state={state} error={error} /> : (
        <>
          <div className="cards">
            <div className="card"><div className="k">Adapters available</div><div className="v mono">{types.length}</div></div>
            <div className="card"><div className="k">Registered</div><div className="v mono">{rows.length}</div></div>
            <div className="card"><div className="k">Deliveries</div><div className="v mono">{deliveries.length}</div></div>
          </div>

          <h2>Register an adapter</h2>
          <details className="panel">
            <summary>New integration</summary>
            <div className="toolbar">
              <label>Name<input aria-label="Integration name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="SAP S/4HANA" /></label>
              <label>Type
                <select aria-label="Integration type" value={form.itype} onChange={(e) => setForm({ ...form, itype: e.target.value })}>
                  {types.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label>Secret ref<input aria-label="Secret reference" value={form.secret_ref} onChange={(e) => setForm({ ...form, secret_ref: e.target.value })} placeholder="env:ERP_TOKEN" /></label>
              <button onClick={register} disabled={busy !== "" || form.name.length < 2}>{busy === "reg" ? "Registering…" : "Register"}</button>
            </div>
          </details>
          <DataTable caption="Registered integrations" rows={rows} rowKey={(r) => r.id} columns={regCols}
            empty={<Empty title="No integrations" hint="Only adapters listed under /integrations/types are accepted." />} />

          <h2 style={{ marginTop: 20 }}>Webhook endpoints</h2>
          <details className="panel">
            <summary>Add endpoint</summary>
            <div className="toolbar">
              <label>URL (https)<input aria-label="Webhook URL" value={whForm.url} onChange={(e) => setWhForm({ ...whForm, url: e.target.value })} placeholder="https://hooks.example.com/vantor" style={{ width: 300 }} /></label>
              <label>Events<input aria-label="Webhook events" value={whForm.events} onChange={(e) => setWhForm({ ...whForm, events: e.target.value })} placeholder="RFQ_AWARDED,PO_APPROVED" /></label>
              <button onClick={addWebhook} disabled={busy !== "" || !whForm.url.startsWith("https://") || whForm.url.length < 9}>
                {busy === "wh" ? "Adding…" : "Add endpoint"}
              </button>
            </div>
            <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>
              HTTP(S) only — <code>http://</code> endpoints are refused. A signed ping verifies the receiver.
            </p>
          </details>

          <div className="toolbar" style={{ marginTop: 10 }}>
            <button className="ghost" onClick={ping} disabled={busy !== "" || rows.length === 0 && deliveries.length === 0}>
              {busy === "ping" ? "Pinging…" : "Test delivery"}
            </button>
          </div>

          <h2 style={{ marginTop: 20 }}>Webhook deliveries</h2>
          <DataTable caption="Webhook deliveries" rows={deliveries} rowKey={(d) => d.id} columns={delCols}
            empty={<Empty title="No deliveries" hint="Only real domain events fan out to endpoints." />} />
        </>
      )}
    </Shell>
  );
}
