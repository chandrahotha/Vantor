"use client";
import { useCallback, useState } from "react";
import Shell from "../../components/Shell";
import { AuthScreen, Badge, DataTable, Empty, ErrorBox, LiveRegion, useBoot, type Column } from "../../components/ui";
import { api, newIdemKey } from "../../lib/api";

type IType = string;
type Integration = { id: string; name: string; itype: IType; status: string; createdAt: string };
type Delivery = { id: string; event: string; status: string; attempts: number };
type Endpoint = { id: string; url: string; events: string[]; status: string };

const TONE: Record<string, "ok" | "warn" | "bad" | "info" | undefined> = {
  active: "ok", disabled: "warn", failed: "bad",
  delivered: "ok", failed_delivery: "bad", pending: "warn",
};

export default function Integrations() {
  const [types, setTypes] = useState<string[]>([]);
  const [rows, setRows] = useState<Integration[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({ name: "", itype: "erp", secret_ref: "" });
  const [whForm, setWhForm] = useState({ url: "", events: "" });

  const load = useCallback(async () => {
    const [t, i, e, d] = await Promise.all([
      api<{ types: string[] }>("/api/v1/integrations/types"),
      api<Integration[]>("/api/v1/integrations"),
      api<Endpoint[]>("/api/v1/webhooks/endpoints"),
      api<Delivery[]>("/api/v1/webhooks/deliveries?limit=25"),
    ]);
    setTypes(t.data?.types || []);
    setRows(i.data || []);
    setEndpoints(e.data || []);
    setDeliveries(d.data || []);
  }, []);

  const { state, error, reload } = useBoot(load);
  const shownErr = err || error;

  async function act(key: string, fn: () => Promise<void>) {
    setBusy(key); setErr(""); setNote("");
    try { await fn(); await load(); } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(""); }
  }

  const register = () => act("reg", async () => {
    await api("/api/v1/integrations", { method: "POST", idemKey: newIdemKey(), body: JSON.stringify(form) });
    setNote(`Integration ${form.name} registered. It starts disabled — an operator enables an adapter during deployment, so nothing begins exchanging data because a form was filled in.`);
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

  /** Send one signed ping to a specific receiver.
   *
   *  This used to POST `/webhooks/test` with no body and read `deliveries` off
   *  the response. The route requires an `endpoint_id` and answers with
   *  `{ delivery }`, so the call 422'd every time; had it succeeded it would
   *  have rendered "Ping delivered to undefined endpoint(s)". The endpoint list
   *  it needed to name a receiver did not exist as an API route either. */
  const ping = (ep: Endpoint) => act(`ping-${ep.id}`, async () => {
    const r = await api<{ delivery: { status: string; attempts: number; error?: string } }>(
      "/api/v1/webhooks/test",
      { method: "POST", idemKey: newIdemKey(), body: JSON.stringify({ endpoint_id: ep.id }) },
    );
    const d = r.data.delivery;
    setNote(
      d.status === "delivered"
        ? `${ep.url} answered the signed ping. Live events will reach it.`
        : `${ep.url} did not accept the ping (${d.status}${d.error ? `: ${d.error}` : ""}). It stays registered; fix the receiver and try again.`,
    );
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

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Integrations</h1>
          <p>Connect other systems to VANTOR, and see what has been delivered to them.</p>
        </div>
      </div>
      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

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
              HTTPS only — <code>http://</code> endpoints are refused, and the address is checked before it
              is stored rather than on the first delivery. Once registered, send it a test ping below to
              confirm the receiver accepts the signature.
            </p>
          </details>

          <DataTable caption="Registered webhook endpoints" rows={endpoints} rowKey={(e) => e.id}
            columns={[
              { key: "url", header: "URL", render: (e) => <span className="mono" style={{ fontSize: 12 }}>{e.url}</span> },
              { key: "events", header: "Events", render: (e) => e.events.length ? e.events.join(", ") : "all events" },
              { key: "status", header: "Status", render: (e) => <Badge tone={TONE[e.status]}>{e.status}</Badge> },
              {
                key: "act", header: "Verify", align: "end", render: (e) => (
                  <button className="ghost" onClick={() => ping(e)} disabled={busy !== ""}>
                    {busy === `ping-${e.id}` ? "Pinging…" : "Send test ping"}
                  </button>
                ),
              },
            ]}
            empty={<Empty title="No endpoints yet" hint="A webhook endpoint is an HTTPS URL VANTOR posts signed events to. Add one above, then send it a test ping to check the receiver accepts the signature." />} />

          <h2 style={{ marginTop: 20 }}>Webhook deliveries</h2>
          <DataTable caption="Webhook deliveries" rows={deliveries} rowKey={(d) => d.id} columns={delCols}
            empty={<Empty title="No deliveries" hint="Only real domain events fan out to endpoints." />} />
    </Shell>
  );
}
