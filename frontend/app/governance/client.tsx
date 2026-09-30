"use client";
import { useCallback, useState } from "react";
import Shell from "../../components/Shell";
import PaletteSwitcher from "../../components/PaletteSwitcher";
import { AuthScreen, Badge, DataTable, Empty, ErrorBox, LiveRegion, Pager, useBoot, type Column } from "../../components/ui";
import { api, newIdemKey } from "../../lib/api";

type Event = {
  id: string; actor: string; action: string; resource: string; resourceId: string;
  occurredAt: string; reason: string; source: string; hash: string; prevHash: string;
};
type Verify = { valid: boolean; message: string; truncated: boolean };
type Category = { id: string; code: string; name: string; parentId: string };
type Item = { id: string; code: string; name: string; uom: string; refPriceMinor: number; currency: string; categoryId: string };

export default function GovernanceClient() {
  const [events, setEvents] = useState<Event[]>([]);
  const [verify, setVerify] = useState<Verify | null>(null);
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [more, setMore] = useState(false);
  const [action, setAction] = useState("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [catForm, setCatForm] = useState({ code: "", name: "", parentId: "" });
  const [itemForm, setItemForm] = useState({ code: "", name: "", uom: "each", refPrice: "", currency: "INR", categoryId: "" });
  const [budForm, setBudForm] = useState({ categoryId: "", period: new Date().toISOString().slice(0, 7), ceiling: "" });

  const period = new Date().toISOString().slice(0, 7);

  const load = useCallback(async (cur: string) => {
    const [ev, vf, cats, its] = await Promise.all([
      api<Event[]>(`/api/v1/audit-events?limit=50&cursor=${encodeURIComponent(cur)}${action ? `&action=${encodeURIComponent(action)}` : ""}`),
      api<Verify>("/api/v1/audit-events/verify"),
      api<Category[]>("/api/v1/catalog/categories"),
      api<Item[]>("/api/v1/catalog/items?limit=50"),
    ]);
    setEvents(ev.data || []);
    setMore(!!ev.pagination?.hasMore);
    setNextCursor(ev.pagination?.nextCursor || "");
    setCursor(cur);
    setVerify(vf.data);
    setCategories(cats.data || []);
    setItems(its.data || []);
  }, [action]);

  const { state, error, reload } = useBoot(() => load(""));
  const shownErr = err || error;

  async function act(key: string, fn: () => Promise<void>) {
    setBusy(key); setErr(""); setNote("");
    try { await fn(); } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(""); }
  }

  const createCategory = () => act("cat", async () => {
    await api("/api/v1/catalog/categories", { method: "POST", idemKey: newIdemKey(), body: JSON.stringify(catForm) });
    setNote(`Category ${catForm.code.toUpperCase()} created.`);
    setCatForm({ code: "", name: "", parentId: "" });
    await load("");
  });

  const createItem = () => act("item", async () => {
    await api("/api/v1/catalog/items", { method: "POST", idemKey: newIdemKey(), body: JSON.stringify({ ...itemForm, ref_price_minor: Math.round(Number(itemForm.refPrice || 0) * 100) }) });
    setNote(`Catalog item ${itemForm.code} created.`);
    setItemForm({ code: "", name: "", uom: "each", refPrice: "", currency: "INR", categoryId: "" });
    await load("");
  });

  const createBudget = () => act("budget", async () => {
    await api("/api/v1/budgets", { method: "POST", idemKey: newIdemKey(), body: JSON.stringify({ category_id: budForm.categoryId, period: budForm.period, ceiling_minor: Math.round(Number(budForm.ceiling || 0) * 100) }) });
    setNote(`Budget ceiling set for ${budForm.categoryId} in ${budForm.period}. Approvals above it now fail with BUDGET_EXCEEDED.`);
    setBudForm({ categoryId: "", period, ceiling: "" });
  });

  const evCols: Column<Event>[] = [
    { key: "when", header: "When", render: (e) => <span className="mono" style={{ fontSize: 12 }}>{new Date(e.occurredAt).toLocaleString()}</span> },
    { key: "actor", header: "Actor", render: (e) => e.actor },
    { key: "action", header: "Action", render: (e) => <Badge tone="info">{e.action}</Badge> },
    { key: "resource", header: "Resource", render: (e) => <span className="mono">{e.resource}{e.resourceId ? `/${e.resourceId.slice(0, 8)}` : ""}</span> },
    { key: "source", header: "Source", render: (e) => e.source },
    { key: "hash", header: "Hash", render: (e) => <span className="mono" style={{ fontSize: 11 }}>{e.hash.slice(0, 12)}…</span> },
  ];

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Governance</h1>
          <p>The record of every change made in this tenant, plus the categories and budget ceilings that constrain spending.</p>
        </div>
      </div>
      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      <div className="cards">
            <div className="card">
              <div className="k">Audit chain</div>
              {/* Unknown is not broken. While the verification call is in
                  flight — or when the backend is unreachable — this rendered a
                  red em dash, so a governance screen reported a tamper-evident
                  audit chain as failing whenever it simply had not been asked
                  yet. */}
              <div className={`v mono${verify ? (verify.valid ? " good" : " bad") : ""}`}>
                {verify ? (verify.valid ? "VERIFIED" : "BROKEN") : "Not checked"}
              </div>
              <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>{verify?.message ?? "The chain could not be verified from here."}</div>
            </div>
            <div className="card"><div className="k">Categories</div><div className="v mono">{categories.length}</div></div>
            <div className="card"><div className="k">Catalog items</div><div className="v mono">{items.length}</div></div>
            <div className="card">
              <div className="k">Budget period</div>
              <div className="v mono" style={{ fontSize: 18 }}>{period}</div>
            </div>
          </div>
          {verify && !verify.valid ? (
            <ErrorBox message={`Audit chain verification failed: ${verify.message}. Treat every derived number on this tenant as suspect until resolved.`} />
          ) : null}

          <h2>Categories</h2>
          <details className="panel">
            <summary>New category</summary>
            <div className="toolbar">
              <label>Code<input aria-label="Category code" value={catForm.code} onChange={(e) => setCatForm({ ...catForm, code: e.target.value })} placeholder="CAT-STEEL" /></label>
              <label>Name<input aria-label="Category name" value={catForm.name} onChange={(e) => setCatForm({ ...catForm, name: e.target.value })} placeholder="Steel and alloys" /></label>
              <label>Parent
                <select aria-label="Parent category" value={catForm.parentId} onChange={(e) => setCatForm({ ...catForm, parentId: e.target.value })}>
                  <option value="">None (top level)</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}
                </select>
              </label>
              <button onClick={createCategory} disabled={busy !== "" || catForm.code.length < 2 || catForm.name.length < 2}>
                {busy === "cat" ? "Creating…" : "Create category"}
              </button>
            </div>
          </details>
          <DataTable caption="Catalog categories" rows={categories} rowKey={(c) => c.id}
            columns={[
              { key: "code", header: "Code", render: (c) => <span className="mono">{c.code}</span> },
              { key: "name", header: "Name", render: (c) => c.name },
              { key: "parent", header: "Parent", render: (c) => (categories.find((p) => p.id === c.parentId)?.code ?? "—") },
            ]}
            empty={<Empty title="No categories" hint="Categories are how spend is grouped for budgets and reporting. Add the first one under “New category” above." />} />

          <h2 style={{ marginTop: 20 }}>Catalog</h2>
          <details className="panel">
            <summary>New catalog item</summary>
            <div className="toolbar">
              <label>Code<input aria-label="Item code" value={itemForm.code} onChange={(e) => setItemForm({ ...itemForm, code: e.target.value })} placeholder="BOLT-M10" /></label>
              <label>Name<input aria-label="Item name" value={itemForm.name} onChange={(e) => setItemForm({ ...itemForm, name: e.target.value })} placeholder="M10 hex bolt" /></label>
              <label>UoM<input aria-label="Unit of measure" value={itemForm.uom} size={6} onChange={(e) => setItemForm({ ...itemForm, uom: e.target.value })} /></label>
              <label>Ref price<input aria-label="Reference price" inputMode="decimal" size={8} value={itemForm.refPrice} onChange={(e) => setItemForm({ ...itemForm, refPrice: e.target.value })} placeholder="5.00" /></label>
              <label>Currency<input aria-label="Item currency" size={5} value={itemForm.currency} onChange={(e) => setItemForm({ ...itemForm, currency: e.target.value.toUpperCase() })} /></label>
              <label>Category
                <select aria-label="Item category" value={itemForm.categoryId} onChange={(e) => setItemForm({ ...itemForm, categoryId: e.target.value })}>
                  <option value="">Uncategorised</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}
                </select>
              </label>
              <button onClick={createItem} disabled={busy !== "" || itemForm.code.length < 2 || itemForm.name.length < 2}>
                {busy === "item" ? "Creating…" : "Create item"}
              </button>
            </div>
          </details>
          <DataTable caption="Catalog items" rows={items} rowKey={(i) => i.id}
            columns={[
              { key: "code", header: "Code", render: (i) => <span className="mono">{i.code}</span> },
              { key: "name", header: "Name", render: (i) => i.name },
              { key: "uom", header: "UoM", render: (i) => i.uom },
              { key: "cat", header: "Category", render: (i) => (categories.find((c) => c.id === i.categoryId)?.code ?? "—") },
              { key: "price", header: "Reference price", numeric: true, render: (i) => (i.refPriceMinor ? `${(i.refPriceMinor / 100).toFixed(2)} ${i.currency}` : "—") },
            ]}
            empty={<Empty title="Catalog is empty" hint="Uncategorised POs are flagged as maverick spend." />} />

          <h2 style={{ marginTop: 20 }}>Budget ceilings</h2>
          <details className="panel">
            <summary>Set a budget ceiling</summary>
            <div className="toolbar">
              <label>Category
                <select aria-label="Budget category" value={budForm.categoryId} onChange={(e) => setBudForm({ ...budForm, categoryId: e.target.value })}>
                  <option value="">Select…</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
                </select>
              </label>
              <label>Period<input aria-label="Budget period" placeholder="YYYY-MM" value={budForm.period} onChange={(e) => setBudForm({ ...budForm, period: e.target.value })} size={9} /></label>
              <label>Ceiling<input aria-label="Budget ceiling" inputMode="decimal" size={10} value={budForm.ceiling} onChange={(e) => setBudForm({ ...budForm, ceiling: e.target.value })} placeholder="100000.00" /></label>
              <button onClick={createBudget} disabled={busy !== "" || !budForm.categoryId || !/^\d{4}-\d{2}$/.test(budForm.period) || !budForm.ceiling}>
                {busy === "budget" ? "Saving…" : "Set ceiling"}
              </button>
            </div>
            <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>
              A ceiling is a hard server-side gate: approving a PO that would exceed it fails with
              <code> BUDGET_EXCEEDED</code>. There is no GET endpoint for budgets yet, so set ceilings
              through this form or <code>POST /api/v1/budgets</code>.
            </p>
          </details>

          <h2 style={{ marginTop: 20 }}>Audit trail</h2>
          <div className="toolbar" role="search">
            <label>Filter by action<input aria-label="Filter audit by action" value={action} onChange={(e) => setAction(e.target.value.toUpperCase())} placeholder="RFQ_AWARDED" /></label>
            <button className="ghost" onClick={() => load("")}>Apply</button>
          </div>
          <DataTable caption="Audit event trail" rows={events} rowKey={(e) => e.id} columns={evCols}
            empty={<Empty title="No audit events match" hint="Every write in this tenant lands here, hash-chained." />} />
          <Pager stack={stack} hasMore={more} busy={busy !== ""}
            onPrev={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv); }}
            onNext={async () => { setStack((s) => [...s, cursor]); await load(nextCursor); }} />

          {/* Appearance is a workspace preference, not a governance control, so
              it goes after the governed material rather than above it. */}
          <hr className="rule" />
          <h2>Workspace appearance</h2>
          <PaletteSwitcher />
    </Shell>
  );
}
