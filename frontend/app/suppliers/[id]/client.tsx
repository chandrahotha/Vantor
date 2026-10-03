"use client";
import Link from "next/link";
import { useCallback, useState } from "react";
import Shell from "../../../components/Shell";
import { AuthScreen, Badge, ConfirmDialog, DataTable, Empty, ErrorBox, LiveRegion, Money, StatCard, useBoot, type Column } from "../../../components/ui";
import { api, fmtMinor, newIdemKey } from "../../../lib/api";
type Supplier = { id: string; code: string; name: string; status: string; country: string; currency: string; riskTier?: string; categoryId?: string; categoryName?: string };
type Contact = { id: string; fullName: string; email: string; phone: string; role: string };
type Scorecard = { supplierId: string; score: number; grade: string; risk_tier: string; dims: Record<string, number> } | null;
type Cert = { id: string; name: string; issuer: string; validUntil: string; status: string };
type Qual = { status: string; exists: boolean; checklist?: { key: string; label: string; done: boolean }[] };
type ContractRow = { id: string; code: string; title: string; status: string; valueMinor: number; currency: string; endDate: string };
type PORow = { id: string; code: string; status: string; totalMinor: number; currency: string };
type InvoiceRow = { id: string; code: string; status: string; totalMinor: number; currency: string; poCode?: string };

const SCORE_DIMS = ["financial", "quality", "delivery", "service", "compliance"] as const;

export default function SupplierDetail({ id }: { id: string }) {
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [scorecard, setScorecard] = useState<Scorecard>(null);
  const [certs, setCerts] = useState<Cert[]>([]);
  const [qual, setQual] = useState<Qual | null>(null);
  const [contracts, setContracts] = useState<ContractRow[]>([]);
  const [pos, setPos] = useState<PORow[]>([]);
  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [contactForm, setContactForm] = useState({ full_name: "", email: "", phone: "", role: "" });
  const [certForm, setCertForm] = useState({ name: "", issuer: "", valid_until: "", document_id: "" });
  const [scoreForm, setScoreForm] = useState<Record<(typeof SCORE_DIMS)[number], string>>({ financial: "3", quality: "3", delivery: "3", service: "3", compliance: "3" });
  const [decisionReason, setDecisionReason] = useState("");
  /** Rejecting a qualification blocks the supplier from being sourced; it is
   *  confirmed, and the dialog is where the reason is asked for, because the
   *  reason is what the audit record will carry. */
  const [confirmReject, setConfirmReject] = useState(false);

  const load = useCallback(async () => {
    const [s, ct, sc, cf, q, contractRows, poRows, invRows] = await Promise.all([
      api<Supplier>(`/api/v1/suppliers/${id}`),
      api<Contact[]>(`/api/v1/suppliers/${id}/contacts`),
      api<Scorecard>(`/api/v1/suppliers/${id}/scorecard`),
      api<Cert[]>(`/api/v1/suppliers/${id}/certifications`),
      api<Qual>(`/api/v1/suppliers/${id}/qualification`),
      // The supplier 360 used to answer only "who is this and are they
      // qualified" — what they have actually been awarded, bought from, and
      // paid for lived on three other pages with no reverse link back here.
      api<ContractRow[]>(`/api/v1/contracts?supplierId=${id}&limit=10`),
      api<PORow[]>(`/api/v1/purchase-orders?supplierId=${id}&limit=10`),
      api<InvoiceRow[]>(`/api/v1/invoices?supplierId=${id}&limit=10`),
    ]);
    setSupplier(s.data);
    setContacts(ct.data || []);
    setScorecard(sc.data);
    setCerts(cf.data || []);
    setQual(q.data);
    setContracts(contractRows.data || []);
    setPos(poRows.data || []);
    setInvoices(invRows.data || []);
  }, [id]);

  const { state, error, reload } = useBoot(load);
  const shownErr = err || error;

  async function act(key: string, fn: () => Promise<void>) {
    setBusy(key); setErr(""); setNote("");
    try { await fn(); await load(); } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(""); }
  }

  const addContact = () => act("contact", async () => {
    await api(`/api/v1/suppliers/${id}/contacts`, { method: "POST", idemKey: newIdemKey(), body: JSON.stringify(contactForm) });
    setNote(`Contact ${contactForm.full_name} added.`);
    setContactForm({ full_name: "", email: "", phone: "", role: "" });
  });

  const addCert = () => act("cert", async () => {
    await api(`/api/v1/suppliers/${id}/certifications`, { method: "POST", idemKey: newIdemKey(), body: JSON.stringify(certForm) });
    setNote(`Certification ${certForm.name} recorded.`);
    setCertForm({ name: "", issuer: "", valid_until: "", document_id: "" });
  });

  const verifyCert = (certId: string, name: string) => act(`cert-${certId}`, async () => {
    await api(`/api/v1/suppliers/${id}/certifications/${certId}/verify`, { method: "POST", idemKey: newIdemKey() });
    setNote(`${name} verified.`);
  });

  const submitScorecard = () => act("score", async () => {
    const dims = Object.fromEntries(SCORE_DIMS.map((d) => [d, Number(scoreForm[d])]));
    await api(`/api/v1/suppliers/${id}/scorecard`, { method: "POST", idemKey: newIdemKey(), body: JSON.stringify({ dims }) });
    setNote("Scorecard saved — grade and risk tier recomputed server-side.");
  });

  const submitQual = () => act("qual", async () => {
    const r = await api<{ status: string }>(`/api/v1/suppliers/${id}/qualification/submit`, { method: "POST", idemKey: newIdemKey() });
    setNote(`Qualification submitted (${r.data.status}).`);
  });

  const decide = (decision: "qualified" | "rejected") => act(`decide-${decision}`, async () => {
    await api(`/api/v1/suppliers/${id}/qualification/decide`, { method: "POST", idemKey: newIdemKey(), body: JSON.stringify({ decision, reason: decisionReason }) });
    setNote(`Qualification ${decision}.`);
    setDecisionReason("");
  });

  const scoresValid = SCORE_DIMS.every((d) => {
    const n = Number(scoreForm[d]);
    return Number.isInteger(n) && n >= 1 && n <= 5;
  });

  const contactCols: Column<Contact>[] = [
    { key: "name", header: "Name", render: (c) => c.fullName },
    { key: "email", header: "Email", render: (c) => c.email || "—" },
    { key: "phone", header: "Phone", render: (c) => c.phone || "—" },
    { key: "role", header: "Role", render: (c) => c.role || "—" },
  ];

  const contractCols: Column<ContractRow>[] = [
    { key: "code", header: "Code", render: (c) => <Link href="/contracts" className="mono">{c.code}</Link> },
    { key: "title", header: "Title", render: (c) => c.title },
    { key: "status", header: "Status", render: (c) => <Badge tone={c.status === "active" ? "ok" : c.status === "terminated" ? "bad" : undefined}>{c.status}</Badge> },
    { key: "end", header: "Ends", render: (c) => c.endDate || "—" },
    { key: "value", header: "Value", numeric: true, render: (c) => <Money>{fmtMinor(c.valueMinor, c.currency)}</Money> },
  ];

  const poCols: Column<PORow>[] = [
    { key: "code", header: "Code", render: (p) => <Link href="/orders" className="mono">{p.code}</Link> },
    { key: "status", header: "Status", render: (p) => <Badge tone={p.status === "invoiced" || p.status === "closed" ? "ok" : undefined}>{p.status}</Badge> },
    { key: "total", header: "Total", numeric: true, render: (p) => <Money>{fmtMinor(p.totalMinor, p.currency)}</Money> },
  ];

  const invoiceCols: Column<InvoiceRow>[] = [
    { key: "code", header: "Code", render: (i) => <Link href="/orders" className="mono">{i.code}</Link> },
    { key: "po", header: "PO", render: (i) => i.poCode || "—" },
    { key: "status", header: "Status", render: (i) => <Badge tone={i.status === "paid" || i.status === "approved" ? "ok" : i.status === "rejected" ? "bad" : undefined}>{i.status}</Badge> },
    { key: "total", header: "Total", numeric: true, render: (i) => <Money>{fmtMinor(i.totalMinor, i.currency)}</Money> },
  ];

  const certCols: Column<Cert>[] = [
    { key: "name", header: "Certification", render: (c) => c.name },
    { key: "issuer", header: "Issuer", render: (c) => c.issuer || "—" },
    { key: "valid", header: "Valid until", render: (c) => c.validUntil || "—" },
    { key: "status", header: "Status", render: (c) => <Badge tone={c.status === "verified" ? "ok" : c.status === "pending" ? "warn" : undefined}>{c.status}</Badge> },
    {
      key: "act", header: "", render: (c) =>
        c.status !== "verified" ? (
          <button className="ghost" onClick={() => verifyCert(c.id, c.name)} disabled={busy !== ""}>
            {busy === `cert-${c.id}` ? "…" : "Verify"}
          </button>
        ) : <span style={{ color: "var(--faint)", fontSize: 12 }}>verified</span>,
    },
  ];

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead">
        <div>
          {/* This is the only route in the app reached *from* another screen,
              and it had no way back to it — the browser's Back button was the
              whole of the affordance. */}
          <p style={{ margin: "0 0 6px" }}>
            <Link href="/suppliers">← All suppliers</Link>
          </p>
          <h1>{supplier ? `${supplier.code} — ${supplier.name}` : "Supplier"}</h1>
          <p>Everything on file for this supplier. Every change here is written to the audit trail.</p>
          {supplier?.categoryName ? <p style={{ color: "var(--muted)", fontSize: 13 }}>Category: {supplier.categoryName}</p> : null}
        </div>
      </div>

      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      {supplier ? (
        <>
          <div className="cards">
            <StatCard label="Status" value={supplier.status} />
            <StatCard label="Score" value={scorecard ? `${scorecard.score}` : "—"} tone={scorecard && scorecard.score >= 70 ? "good" : undefined} />
            <StatCard label="Grade" value={scorecard?.grade ?? "—"} />
            <StatCard label="Risk tier" value={scorecard?.risk_tier ?? "—"} tone={scorecard?.risk_tier === "high" ? "bad" : undefined} />
          </div>

          <h2>Qualification</h2>
          <div className="panel">
            <p>
              Current state: <Badge tone={qual?.status === "qualified" ? "ok" : qual?.status === "rejected" ? "bad" : "warn"}>{qual?.status ?? "draft"}</Badge>
            </p>
            {qual?.checklist?.length ? (
              <ul>
                {qual.checklist.map((c) => <li key={c.key}>{c.done ? "✔" : "✘"} {c.label}</li>)}
              </ul>
            ) : null}
            <div className="toolbar">
              {qual?.status !== "under_review" && qual?.status !== "qualified" ? (
                <button onClick={submitQual} disabled={busy !== ""}>{busy === "qual" ? "Submitting…" : "Submit for review"}</button>
              ) : null}
              {qual?.status === "under_review" ? (
                <>
                  <label>Decision reason
                    <input aria-label="Decision reason" value={decisionReason} onChange={(e) => setDecisionReason(e.target.value)} placeholder="Recorded in the audit trail (optional)" style={{ minWidth: 260 }} />
                  </label>
                  <button onClick={() => decide("qualified")} disabled={busy !== ""}>
                    {busy === "decide-qualified" ? "Qualifying…" : "Qualify supplier"}
                  </button>
                  <button className="ghost" onClick={() => setConfirmReject(true)} disabled={busy !== ""}>Reject supplier</button>
                </>
              ) : null}
            </div>
          </div>

          <h2>Scorecard</h2>
          {scorecard ? (
            <ul>
              {Object.entries(scorecard.dims).map(([k, v]) => <li key={k}>{k}: {v}/5</li>)}
            </ul>
          ) : <p style={{ color: "var(--muted)" }}>No scorecard yet. Score the five dimensions below (1–5 each).</p>}
          <div className="toolbar">
            {/* The server scores each dimension 1–5. These were free-text boxes,
                so "seven" or "-2" reached the API and came back as a 422 with
                no indication of which box was wrong. */}
            {SCORE_DIMS.map((d) => (
              <label key={d} style={{ textTransform: "capitalize" }}>{d}
                <input
                  aria-label={`${d} score, 1 to 5`}
                  type="number"
                  min={1}
                  max={5}
                  step={1}
                  inputMode="numeric"
                  style={{ width: 72 }}
                  value={scoreForm[d]}
                  onChange={(e) => setScoreForm({ ...scoreForm, [d]: e.target.value })}
                />
              </label>
            ))}
            <button onClick={submitScorecard} disabled={busy !== "" || !scoresValid}>
              {busy === "score" ? "Scoring…" : "Save scorecard"}
            </button>
            {!scoresValid ? (
              <span style={{ color: "var(--warn)", fontSize: 12, alignSelf: "center" }} role="status">
                Each dimension must be a whole number from 1 to 5.
              </span>
            ) : null}
          </div>

          <h2>Certifications</h2>
          <details className="panel">
            <summary>Record certification</summary>
            <div className="toolbar">
              <label>Name<input aria-label="Certification name" value={certForm.name} onChange={(e) => setCertForm({ ...certForm, name: e.target.value })} placeholder="ISO 9001" /></label>
              <label>Issuer<input aria-label="Certification issuer" value={certForm.issuer} onChange={(e) => setCertForm({ ...certForm, issuer: e.target.value })} placeholder="BSI" /></label>
              <label>Valid until<input aria-label="Valid until" value={certForm.valid_until} onChange={(e) => setCertForm({ ...certForm, valid_until: e.target.value })} placeholder="2027-12-31" /></label>
              <button onClick={addCert} disabled={busy !== "" || certForm.name.length < 2}>{busy === "cert" ? "Saving…" : "Record"}</button>
            </div>
          </details>
          <DataTable caption="Certifications" rows={certs} rowKey={(c) => c.id} columns={certCols}
            empty={<Empty title="No certifications" />} />

          <h2 style={{ marginTop: 20 }}>Contacts</h2>
          <details className="panel">
            <summary>Add contact</summary>
            <div className="toolbar">
              <label>Name<input aria-label="Contact name" value={contactForm.full_name} onChange={(e) => setContactForm({ ...contactForm, full_name: e.target.value })} placeholder="Jane Doe" /></label>
              <label>Email<input aria-label="Contact email" value={contactForm.email} onChange={(e) => setContactForm({ ...contactForm, email: e.target.value })} placeholder="jane@supplier.com" /></label>
              <label>Phone<input aria-label="Contact phone" value={contactForm.phone} onChange={(e) => setContactForm({ ...contactForm, phone: e.target.value })} placeholder="+91…" /></label>
              <label>Role<input aria-label="Contact role" value={contactForm.role} onChange={(e) => setContactForm({ ...contactForm, role: e.target.value })} placeholder="Sales" /></label>
              <button onClick={addContact} disabled={busy !== "" || contactForm.full_name.length < 2}>{busy === "contact" ? "Adding…" : "Add contact"}</button>
            </div>
          </details>
          <DataTable caption="Contacts" rows={contacts} rowKey={(c) => c.id} columns={contactCols}
            empty={<Empty title="No contacts yet" />} />

          {/* The 360 used to stop at "who is this and are they qualified" —
              what this supplier has actually been awarded, bought from and
              paid lived on three separate pages with no link back here. */}
          <h2 style={{ marginTop: 20 }}>Contracts</h2>
          <DataTable caption="Contracts with this supplier" rows={contracts} rowKey={(c) => c.id} columns={contractCols}
            empty={<Empty title="No contracts with this supplier" />} />

          <h2 style={{ marginTop: 20 }}>Purchase orders</h2>
          <DataTable caption="Purchase orders with this supplier" rows={pos} rowKey={(p) => p.id} columns={poCols}
            empty={<Empty title="No purchase orders with this supplier" />} />

          <h2 style={{ marginTop: 20 }}>Invoices</h2>
          <DataTable caption="Invoices from this supplier" rows={invoices} rowKey={(i) => i.id} columns={invoiceCols}
            empty={<Empty title="No invoices from this supplier" />} />
        </>
      ) : <Empty title="Supplier not found" hint="It may be outside your tenant." />}

      <ConfirmDialog
        open={confirmReject}
        title={`Reject ${supplier?.code ?? "this supplier"}?`}
        confirmLabel="Reject supplier"
        tone="danger"
        busy={busy === "decide-rejected"}
        onCancel={() => setConfirmReject(false)}
        onConfirm={async () => { setConfirmReject(false); await decide("rejected"); }}
        body={
          <>
            <strong>{supplier?.name}</strong> will be marked <strong>rejected</strong> and cannot be
            sourced, quoted or contracted until the qualification is resubmitted and decided again.
            <br />
            <br />
            {decisionReason.trim()
              ? <>Reason recorded in the audit chain: “{decisionReason.trim()}”.</>
              : <>No reason has been entered. Cancel and add one if this decision needs to be explainable later.</>}
          </>
        }
      />
    </Shell>
  );
}
