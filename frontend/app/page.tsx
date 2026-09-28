"use client";
import { useCallback, useState } from "react";
import Link from "next/link";
import Shell from "../components/Shell";
import { AuthScreen, Badge, DataTable, Empty, ErrorBox, LiveRegion, MetricCard, useBoot, type Column } from "../components/ui";
import { api, fmtMinor } from "../lib/api";
import { getSession } from "../lib/auth";

type Summary = {
  // VNT-043: nullable. When more than one currency is in play the API refuses to
  // emit a cross-currency total, because summing INR and USD produces a number
  // that looks like money and is not. A client that ignored the null would render
  // NaN, so the type says `null` and every read below handles it.
  poTotalMinor: number | null; invoicedTotalMinor: number | null; savedMinor?: number | null;
  totalsArePerCurrency?: boolean;
  byCurrency: { committed: Record<string, number>; invoiced: Record<string, number>; saved: Record<string, number> };
  currencyCount: number;
};
type Contract = { id: string; code: string; title: string; endDate: string; status: string };
type Rfq = { id: string; code: string; title: string; status: string };
type PO = { id: string; code: string; status: string; totalMinor: number; currency: string };
type Page<T> = { items: T[]; more: boolean };

export default function Dashboard() {
  const [spend, setSpend] = useState<Summary | null>(null);
  const [expiring, setExpiring] = useState<Contract[]>([]);
  const [expiringMore, setExpiringMore] = useState(false);
  const [openRfqs, setOpenRfqs] = useState<Page<Rfq>>({ items: [], more: false });
  const [orders, setOrders] = useState<Page<PO>>({ items: [], more: false });
  const [partial, setPartial] = useState("");

  const load = useCallback(async () => {
    // Each panel settles independently so one failing endpoint does not blank the
    // dashboard — but a total failure is reported as an error, not as "no data".
    // Explicit tuple (not a spread) so each settled result keeps its own type.
    const [sp, ex, rqSent, rqResponse, po] = await Promise.allSettled([
      api<Summary>("/api/v1/spend/summary"),
      // VNT-041: `expiring=true` is now a live 90-day calculation rather than a
      // stored status, and `limit=100` with the hasMore flag makes the count
      // honest — it used to fetch 5 rows and render `expiring.length` as if it
      // were the total, so a tenant with 23 expiring contracts was told 5.
      api<Contract[]>("/api/v1/contracts?expiring=true&limit=100"),
      api<Rfq[]>("/api/v1/rfqs?status=sent&limit=100"),
      api<Rfq[]>("/api/v1/rfqs?status=response&limit=100"),
      api<PO[]>("/api/v1/purchase-orders?limit=5"),
    ]);
    const failed: string[] = [];
    const reasons: string[] = [];
    /** Record *why* a panel failed, not just which one.
     *
     *  This used to keep only the panel name, so a total outage produced
     *  "some live panels could not reach backend: spend, contracts, …" — five
     *  failures, zero reasons, and no way to tell a 401 from a 503 from the
     *  backend not running. Each reason carries the status and the request id,
     *  which is what the backend's own log line is keyed on, so the report can
     *  be matched to a log entry instead of guessed at. */
    const why = (panel: string, e: unknown) => {
      failed.push(panel);
      const err = e as { status?: number; code?: string; requestId?: string; message?: string };
      const status = typeof err?.status === "number" && err.status > 0 ? `${err.status} ` : "";
      const id = err?.requestId ? ` [${err.requestId}]` : "";
      reasons.push(`${panel}: ${status}${err?.message || err?.code || "failed"}${id}`);
    };
    if (sp.status === "fulfilled") setSpend(sp.value.data); else why("spend", sp.reason);
    if (ex.status === "fulfilled") {
      setExpiring(ex.value.data || []);
      setExpiringMore(!!ex.value.pagination?.hasMore);
    } else why("contracts", ex.reason);

    // "Open RFQ" is a real count, not a 5-row sample. `limit=100` plus the
    // hasMore flag gives an exact count below 100 and "100+" above it, where the
    // previous code counted a 5-row sample and labelled it a total.
    const rfqItems: Rfq[] = [];
    let rfqMore = false;
    for (const [name, res] of [["sent", rqSent], ["response", rqResponse]] as const) {
      if (res.status === "fulfilled") {
        rfqItems.push(...(res.value.data || []));
        if (res.value.pagination?.hasMore) rfqMore = true;
      } else {
        why(`rfq:${name}`, res.reason);
      }
    }
    setOpenRfqs({ items: rfqItems.sort((a, b) => a.code.localeCompare(b.code)), more: rfqMore });

    if (po.status === "fulfilled") setOrders({ items: po.value.data || [], more: !!po.value.pagination?.hasMore });
    else why("purchase orders", po.reason);

    // VNT-033. This used to substitute a hardcoded spend total, three contracts,
    // two RFQs and two POs whenever all five panels failed — so an unreachable
    // backend produced a dashboard of invented money and invented suppliers that
    // looked exactly like a working one. A total failure is now reported as a
    // failure: the panels keep their empty state and the notice below is shown.
    // With the reason attached, not just the panel name.
    setPartial(
      failed.length
        ? `Notice — ${failed.length} of 5 live panels could not be loaded. ${reasons.join(" · ")}`
        : "",
    );
  }, []);

  const { state, error, reload } = useBoot(load);

  const ccys = spend ? Object.keys(spend.byCurrency?.committed ?? {}) : [];
  const mixed = (spend?.currencyCount ?? 0) > 1;

  const attention: { key: string; label: string; kind: string; tone: "warn" | "info"; href: string }[] = [
    ...expiring.map((c) => ({ key: c.id, label: `${c.code} — ${c.title}${c.endDate ? ` (ends ${c.endDate})` : ""}`, kind: "Contract", tone: "warn" as const, href: "/contracts" })),
    ...openRfqs.items.map((r) => ({ key: r.id, label: `${r.code} — ${r.title}`, kind: `RFQ · ${r.status}`, tone: "info" as const, href: "/rfqs" })),
  ];

  const attentionCols: Column<(typeof attention)[number]>[] = [
    { key: "item", header: "Item", render: (a) => <Link href={a.href}>{a.label}</Link> },
    { key: "kind", header: "Type", render: (a) => a.kind },
    { key: "status", header: "Status", render: (a) => <Badge tone={a.tone}>needs action</Badge> },
  ];

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  const session = getSession();

  return (
    <Shell user={session ? { name: session.name, tenant: session.tenant } : undefined}>
      <div className="pagehead">
        <div>
          <h1>Procurement Health & Spend Intelligence</h1>
          <p>Live multi-currency commitments, contract renewal monitors, and active RFQ sourcing pipelines.</p>
        </div>
        <div className="pagehead-actions">
          <Link href="/rfqs" className="btn btn-ghost btn-md">View RFQs</Link>
          <Link href="/orders" className="btn btn-primary btn-md">Purchase Orders</Link>
        </div>
      </div>

      <LiveRegion>{error ? <ErrorBox message={error} /> : null}{partial ? <ErrorBox message={partial} /> : null}</LiveRegion>

      <div className="cards">
        {mixed && ccys.length > 0 ? (
          ccys.map((c) => (
            <MetricCard
              key={c}
              label={`Committed (${c})`}
              value={fmtMinor(spend?.byCurrency.committed[c] ?? 0, c)}
              hint="Sum of every purchase order raised in this currency, whatever its approval state."
            />
          ))
        ) : (
          <>
            {/* VNT-043: the API returns null for a cross-currency total rather
                than a wrong number, so the null is rendered as a fact about the
                data instead of being formatted into "NaN". */}
            <MetricCard
              label="Committed (POs)"
              value={!spend ? "—"
                : spend.poTotalMinor == null ? "per currency"
                : fmtMinor(spend.poTotalMinor, ccys[0])}
              hint="Sum of every purchase order raised in this currency, whatever its approval state."
            />
            <MetricCard
              label="Invoiced (approved)"
              value={!spend ? "—"
                : spend.invoicedTotalMinor == null ? "per currency"
                : fmtMinor(spend.invoicedTotalMinor, ccys[0])}
              hint="Only invoices that passed three-way match. Unmatched invoices are not counted here."
            />
          </>
        )}
        <MetricCard
          label="Contracts expiring (90 days)"
          value={expiring.length ? `${expiring.length}${expiringMore ? "+" : ""}` : "0"}
          tone={expiring.length ? "warn" : "good"}
          hint="Computed live against contract end dates — not a stored status. “+” means the count exceeds 100."
        />
        <MetricCard
          label="Open RFQs"
          value={openRfqs.more ? `${openRfqs.items.length}+` : String(openRfqs.items.length)}
          tone={openRfqs.items.length ? "warn" : "good"}
          hint="RFQs in sent or response state, awaiting quotes or evaluation."
        />
      </div>
      {mixed ? (
        <div className="info-callout">
          <span className="info-callout-icon">ℹ</span>
          <span>{spend?.currencyCount} currencies in play — totals are tracked per currency and never summed across denominations.</span>
        </div>
      ) : null}
      <div className="info-callout">
        <span className="info-callout-icon">ℹ</span>
        <span>Contract expiry (90 days) is computed live against contract end dates in the tenant&apos;s active timezone.</span>
      </div>

      <h2>What needs attention</h2>
      <DataTable caption="Items needing attention" rows={attention} rowKey={(a) => a.key} columns={attentionCols}
        empty={<Empty title="Nothing pending" hint="Expiring contracts and open RFQs appear here automatically." />} />

      <h2 style={{ marginTop: 20 }}>Latest purchase orders</h2>
      <DataTable caption="Latest purchase orders" rows={orders.items} rowKey={(o) => o.id}
        columns={[
          { key: "code", header: "Code", render: (o) => <span className="mono">{o.code}</span> },
          { key: "status", header: "Status", render: (o) => <Badge tone={o.status === "approved" || o.status === "sent" ? "ok" : undefined}>{o.status}</Badge> },
          { key: "total", header: "Total", numeric: true, render: (o) => fmtMinor(o.totalMinor, o.currency) },
        ]}
        empty={<Empty title="No purchase orders yet" hint="Create one from the Purchase orders page." />} />
    </Shell>
  );
}
