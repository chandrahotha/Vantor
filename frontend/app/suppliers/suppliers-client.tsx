"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Shell from "../../components/Shell";
import { AuthScreen, Badge, DataTable, Empty, ErrorBox, LiveRegion, Pager, useBoot, type Column } from "../../components/ui";
import { api, newIdemKey } from "../../lib/api";

type Supplier = { id: string; code: string; name: string; status: string; country: string; currency: string; riskTier?: string };

export default function SuppliersClient() {
  const [rows, setRows] = useState<Supplier[]>([]);
  const [cursor, setCursor] = useState("");
  const [nextCursor, setNextCursor] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [more, setMore] = useState(false);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("created_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const rowRefs = useRef<Record<string, HTMLElement | null>>({});

  const load = useCallback(async (cur: string, q: string, s: string, o: string) => {
    const r = await api<Supplier[]>(
      `/api/v1/suppliers?limit=15&cursor=${encodeURIComponent(cur)}&search=${encodeURIComponent(q)}&sort=${s}&order=${o}`,
    );
    setRows(r.data || []);
    setMore(!!r.pagination?.hasMore);
    setNextCursor(r.pagination?.nextCursor || "");
    setCursor(cur);
  }, []);

  const { state, error, reload } = useBoot(() => load("", "", "created_at", "desc"));
  const shownErr = err || error;

  // Command-palette deep link: ?highlight=<id> jumps to and focuses the row.
  // Read via useSearchParams (inside a Suspense boundary on the server wrapper)
  // rather than window.location in an effect. The active highlight is *derived*
  // from the URL, not mirrored into state: `dismissedFor` records which id timed
  // out, so a new deep link re-arms without a reset effect or a setState cascade.
  const searchParams = useSearchParams();
  const deepLink = searchParams.get("highlight") ?? "";
  const [dismissedFor, setDismissedFor] = useState<string | null>(null);
  const highlight = deepLink && dismissedFor !== deepLink ? deepLink : "";

  useEffect(() => {
    if (!highlight || rows.length === 0) return;
    const el = rowRefs.current[highlight];
    if (!el) return;
    el.scrollIntoView({ block: "center" });
    el.focus?.();
    const t = setTimeout(() => setDismissedFor(highlight), 6000);
    return () => clearTimeout(t);
  }, [highlight, rows]);

  function resort(col: string) {
    const o = sort === col && order === "desc" ? "asc" : "desc";
    setSort(col); setOrder(o); setStack([]); load("", search, col, o).catch((e: unknown) => setErr(String(e)));
  }

  function searchNow() { setStack([]); load("", search, sort, order).catch((e: unknown) => setErr(String(e))); }

  async function createSupplier() {
    setBusy("create"); setErr(""); setNote("");
    try {
      const code = (form.code || "").toUpperCase();
      await api("/api/v1/suppliers", { method: "POST", idemKey: newIdemKey(), body: JSON.stringify(form) });
      setNote(`${code} created as a draft. Submit it for qualification from the API to activate it.`);
      setForm({ code: "", name: "", country: "", currency: "INR" });
      await load("", search, sort, order);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy("");
    }
  }

  const [form, setForm] = useState({ code: "", name: "", country: "", currency: "INR" });

  const columns: Column<Supplier>[] = [
    {
      key: "code", header: "Code", sortable: true,
      render: (r) => (
        <Link href={`/suppliers/${r.id}`}>
          <span className="mono" ref={(el) => { rowRefs.current[r.id] = el; }} tabIndex={r.id === highlight ? -1 : undefined}>
            {r.code}
            {r.id === highlight ? <span className="badge info">from palette</span> : null}
          </span>
        </Link>
      ),
    },
    { key: "name", header: "Name", sortable: true, render: (r) => <Link href={`/suppliers/${r.id}`}>{r.name}</Link> },
    {
      key: "status", header: "Status", sortable: true,
      render: (r) => <Badge tone={r.status === "active" ? "ok" : r.status === "blocked" ? "bad" : undefined}>{r.status}</Badge>,
    },
    { key: "country", header: "Country", render: (r) => r.country || "—" },
    { key: "currency", header: "Currency", render: (r) => r.currency || "—" },
  ];

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Suppliers</h1>
          <p>Global vendor master directory: supplier qualification ratings, ESG risk scorecards, multi-currency terms, and active audit history.</p>
        </div>
      </div>
      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}{note ? <div className="banner" role="status">{note}</div> : null}</LiveRegion>

      <details className="panel">
        <summary>New supplier</summary>
        <div className="toolbar">
          <label>Code<input aria-label="Supplier code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="SUP-001" /></label>
          <label>Name<input aria-label="Supplier name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Apex Industrial Technologies" /></label>
          <label>Country<input aria-label="Country" value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} size={6} /></label>
          <label>Currency<input aria-label="Currency" value={form.currency} size={5} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></label>
          <button onClick={createSupplier} disabled={busy !== "" || form.code.length < 2 || form.name.length < 2}>
            {busy === "create" ? "Creating…" : "Create supplier"}
          </button>
        </div>
      </details>

      <div className="toolbar" role="search">
        <label>Search<input type="search" aria-label="Search suppliers" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") searchNow(); }} placeholder="Code or name" /></label>
        <button className="ghost" onClick={searchNow}>Search</button>
      </div>

      <DataTable caption="Supplier list" rows={rows} rowKey={(r) => r.id} columns={columns}
        sort={sort} order={order} onSort={resort}
        empty={<Empty title="No suppliers found" hint="Create one above, or adjust the search." />} />
      <Pager stack={stack} hasMore={more}
        onPrev={async () => { const st = [...stack]; const pv = st.pop() || ""; setStack(st); await load(pv, search, sort, order); }}
        onNext={async () => { setStack((s) => [...s, cursor]); await load(nextCursor, search, sort, order); }} />
    </Shell>
  );
}
