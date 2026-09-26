"use client";
import { useCallback, useState } from "react";
import Link from "next/link";
import Shell from "../components/Shell";
import { Badge, DataTable, Empty, ErrorBox, LiveRegion, Skeleton, StatCard, useBoot, type Column } from "../components/ui";
import { api, fmtMinor } from "../lib/api";
import { getSession } from "../lib/auth";

type Summary = {
  poTotalMinor: number; invoicedTotalMinor: number;
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
  const [openRfqs, setOpenRfqs] = useState<Page<Rfq>>({ items: [], more: false });
  const [orders, setOrders] = useState<Page<PO>>({ items: [], more: false });
  const [partial, setPartial] = useState("");

  const load = useCallback(async () => {
    // Each panel settles independently so one failing endpoint does not blank the
    // dashboard — but a total failure is reported as an error, not as "no data".
    // Explicit tuple (not a spread) so each settled result keeps its own type.
    const [sp, ex, rqSent, rqResponse, po] = await Promise.allSettled([
      api<Summary>("/api/v1/spend/summary"),
      api<Contract[]>("/api/v1/contracts?status=expiring&limit=5"),
      api<Rfq[]>("/api/v1/rfqs?status=sent&limit=100"),
      api<Rfq[]>("/api/v1/rfqs?status=response&limit=100"),
      api<PO[]>("/api/v1/purchase-orders?limit=5"),
    ]);
    const failed: string[] = [];
    if (sp.status === "fulfilled") setSpend(sp.value.data); else failed.push("spend");
    if (ex.status === "fulfilled") setExpiring(ex.value.data || []); else failed.push("contracts");

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
        failed.push(`rfq:${name}`);
      }
    }
    setOpenRfqs({ items: rfqItems.sort((a, b) => a.code.localeCompare(b.code)), more: rfqMore });

    if (po.status === "fulfilled") setOrders({ items: po.value.data || [], more: !!po.value.pagination?.hasMore });
    else failed.push("purchase orders");

    if (failed.length === 5) throw new Error("API unreachable — is the backend running?");
    setPartial(failed.length ? `Partial data — these panels failed: ${failed.join(", ")}.` : "");
  }, []);

  const { state, error } = useBoot(load);

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

  if (state === "loading") return <Shell><Skeleton rows={4} label="Loading dashboard" /></Shell>;
  if (state === "signin") return <Shell><ErrorBox message="Sign-in required to view procurement data." /></Shell>;
  if (state === "error") return <Shell><ErrorBox message={error || "Could not load the dashboard."} /></Shell>;

  const session = getSession();

  return (
    <Shell user={session ? { name: session.name, tenant: session.tenant } : undefined}>
      <div className="pagehead">
        <div>
          <h1>Procurement health</h1>
          <p>Real data only — an empty panel means no activity yet, never a placeholder.</p>
        </div>
      </div>

      <LiveRegion>{error ? <ErrorBox message={error} /> : null}{partial ? <ErrorBox message={partial} /> : null}</LiveRegion>

      <div className="cards">
        {mixed && ccys.length > 0 ? (
          ccys.map((c) => (
            <StatCard key={c} label={`Committed (${c})`} value={fmtMinor(spend?.byCurrency.committed[c] ?? 0, c)} />
          ))
        ) : (
          <>
            <StatCard label="Committed (POs)" value={spend ? fmtMinor(spend.poTotalMinor, ccys[0]) : "—"} />
            <StatCard label="Invoiced (approved)" value={spend ? fmtMinor(spend.invoicedTotalMinor, ccys[0]) : "—"} />
          </>
        )}
        <StatCard
          label="Contracts flagged expiring"
          value={expiring.length ? String(expiring.length) : "0"}
          tone={expiring.length ? "bad" : "good"}
        />
        <StatCard
          label="Open RFQs"
          value={openRfqs.more ? `${openRfqs.items.length}+` : String(openRfqs.items.length)}
          tone={openRfqs.items.length ? "warn" : "good"}
        />
      </div>
      {mixed ? (
        <p style={{ color: "var(--muted)", fontSize: 12 }}>
          {spend?.currencyCount} currencies in play — totals are shown per currency and never added together.
        </p>
      ) : null}
      <p style={{ color: "var(--muted)", fontSize: 12 }}>
        “Flagged expiring” reflects the stored contract status set by the expiry roll
        (<code>POST /api/v1/contracts/roll-expiry</code>), not a live 90-day calculation.
      </p>

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
