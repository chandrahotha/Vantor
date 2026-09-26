"use client";
import { useCallback, useState } from "react";
import Shell from "../../../components/Shell";
import { AuthScreen, Badge, DataTable, Empty, ErrorBox, LiveRegion, StatCard, useBoot, type Column } from "../../../components/ui";
import { api, newIdemKey } from "../../../lib/api";
type Supplier = { id: string; code: string; name: string; status: string; country: string; currency: string; riskTier?: string };
type Contact = { id: string; fullName: string; email: string; phone: string; role: string };
type Scorecard = { supplierId: string; score: number; grade: string; risk_tier: string; dims: Record<string, number> } | null;
type Cert = { id: string; name: string; issuer: string; validUntil: string; status: string };
type Qual = { status: string; exists: boolean; checklist?: { key: string; label: string; done: boolean }[] };

const SCORE_DIMS = ["financial", "quality", "delivery", "service", "compliance"] as const;

export default function SupplierDetail({ id }: { id: string }) {
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [scorecard, setScorecard] = useState<Scorecard>(null);
  const [certs, setCerts] = useState<Cert[]>([]);
  const [qual, setQual] = useState<Qual | null>(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [contactForm, setContactForm] = useState({ full_name: "", email: "", phone: "", role: "" });
  const [certForm, setCertForm] = useState({ name: "", issuer: "", valid_until: "", document_id: "" });
  const [scoreForm, setScoreForm] = useState<Record<(typeof SCORE_DIMS)[number], string>>({ financial: "3", quality: "3", delivery: "3", service: "3", compliance: "3" });
  const [decisionReason, setDecisionReason] = useState("");

  const load = useCallback(async () => {
    const [s, ct, sc, cf, q] = await Promise.all([
      api<Supplier>(`/api/v1/suppliers/${id}`),
      api<Contact[]>(`/api/v1/suppliers/${id}/contacts`),
      api<Scorecard>(`/api/v1/suppliers/${id}/scorecard`),
      api<Cert[]>(`/api/v1/suppliers/${id}/certifications`),
      api<Qual>(`/api/v1/suppliers/${id}/qualification`),
    ]);
    setSupplier(s.data);
    setContacts(ct.data || []);
    setScorecard(sc.data);
    setCerts(cf.data || []);
    setQual(q.data);
  }, [id]);

  const { state, error } = useBoot(load);
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

  const contactCols: Column<Contact>[] = [
    { key: "name", header: "Name", render: (c) => c.fullName },
    { key: "email", header: "Email", render: (c) => c.email || "—" },
    { key: "phone", header: "Phone", render: (c) => c.phone || "—" },
    { key: "role", header: "Role", render: (c) => c.role || "—" },
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

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>{supplier ? `${supplier.code} — ${supplier.name}` : "Supplier"}</h1>
          <p>360° view: contacts, certifications, scorecard and qualification state. All changes are audited.</p>
        </div>
      </div>

      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      {state !== "ok" ? <AuthScreen state={state} error={error} /> : supplier ? (
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
                  <input aria-label="Decision reason" value={decisionReason} onChange={(e) => setDecisionReason(e.target.value)} placeholder="Decision reason (optional)" />
                  <button className="ghost" onClick={() => decide("qualified")} disabled={busy !== ""}>Qualify</button>
                  <button className="ghost" onClick={() => decide("rejected")} disabled={busy !== ""}>Reject</button>
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
            {SCORE_DIMS.map((d) => (
              <label key={d}>{d}
                <input aria-label={`${d} score`} inputMode="numeric" size={3} value={scoreForm[d]} onChange={(e) => setScoreForm({ ...scoreForm, [d]: e.target.value })} />
              </label>
            ))}
            <button onClick={submitScorecard} disabled={busy !== ""}>{busy === "score" ? "Scoring…" : "Save scorecard"}</button>
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
        </>
      ) : <Empty title="Supplier not found" hint="It may be outside your tenant." />}
    </Shell>
  );
}
