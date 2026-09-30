"use client";
import { useCallback, useState } from "react";
import Shell from "../../components/Shell";
import { AuthScreen, DataTable, Empty, ErrorBox, LiveRegion, Money, useBoot, type Column } from "../../components/ui";
import { api, fmtMinor, newIdemKey } from "../../lib/api";

type Round = {
  round: number;
  offer_minor?: number;
  counter_minor?: number;
  buyer?: number;
  supplier?: number;
  event?: string;
};
type SimResult = {
  result: string;
  score: number;
  rounds: Round[];
  reason?: string;
  settled_minor?: number | null;
};

export default function NegoSim() {
  // The round table used to format every figure as INR regardless of what the
  // user was modelling, on a screen whose inputs are otherwise unlabelled
  // numbers. The currency is an input now, so the output states the
  // denomination it was given rather than assuming one.
  const [form, setForm] = useState({ listPrice: "100000.00", walkAway: "75000.00", offers: "70000\n80000\n88000", maxRounds: "5", concessionBp: "1500", currency: "INR" });
  const [out, setOut] = useState<SimResult | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const { state, error, reload } = useBoot(useCallback(async () => {}, []));
  const shownErr = err || error;

  async function run() {
    setBusy(true); setErr("");
    const listPriceNum = Number(form.listPrice);
    const walkAwayNum = Number(form.walkAway);
    if (listPriceNum <= 0 || isNaN(listPriceNum)) {
      setErr("Supplier list price must be greater than zero.");
      setBusy(false);
      return;
    }
    if (walkAwayNum <= 0 || isNaN(walkAwayNum)) {
      setErr("Supplier walk-away floor must be greater than zero.");
      setBusy(false);
      return;
    }
    if (walkAwayNum >= listPriceNum) {
      setErr(`Supplier reserve floor (${walkAwayNum}) must be less than list price (${listPriceNum}) to model concession room.`);
      setBusy(false);
      return;
    }

    try {
      const offers = form.offers.split(/\n+/).map((s) => s.trim()).filter(Boolean).map((v) => Math.round(Number(v) * 100));
      if (offers.length === 0) {
        setErr("Please provide at least one buyer offer.");
        setBusy(false);
        return;
      }
      const r = await api<SimResult>("/api/v1/ai/negotiate", {
        method: "POST", idemKey: newIdemKey(),
        body: JSON.stringify({
          list_price_minor: Math.round(Number(form.listPrice) * 100),
          walk_away_minor: Math.round(Number(form.walkAway) * 100),
          buyer_offers_minor: offers,
          max_rounds: Number(form.maxRounds),
          concession_bp: Number(form.concessionBp),
        }),
      });
      setOut(r.data);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setBusy(false);
    }
  }

  const roundCols: Column<Round>[] = [
    { key: "r", header: "Round", numeric: true, render: (x) => x.round },
    { key: "offer", header: "Your offer", numeric: true, render: (x) => <Money>{fmtMinor(x.buyer ?? x.offer_minor ?? 0, form.currency)}</Money> },
    { key: "counter", header: "Supplier counter", numeric: true, render: (x) => <Money>{fmtMinor(x.supplier ?? x.counter_minor ?? 0, form.currency)}</Money> },
    { key: "event", header: "Status", render: (x) => x.event ? <span className="badge">{x.event.replace("_", " ")}</span> : null },
  ];

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Negotiation simulator</h1>
          <p>Rehearse a price negotiation before you have it. Nothing here touches real procurement data.</p>
        </div>
      </div>
      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}</LiveRegion>

      <div className="panel">
            <div className="toolbar">
              <label>Currency<input aria-label="Currency" size={5} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></label>
              <label>Supplier list price<input aria-label="List price" inputMode="decimal" value={form.listPrice} onChange={(e) => setForm({ ...form, listPrice: e.target.value })} /></label>
              <label>Supplier walk-away floor<input aria-label="Walk-away price" inputMode="decimal" value={form.walkAway} onChange={(e) => setForm({ ...form, walkAway: e.target.value })} /></label>
              <label>Max rounds<input aria-label="Max rounds" inputMode="numeric" size={4} value={form.maxRounds} onChange={(e) => setForm({ ...form, maxRounds: e.target.value })} /></label>
              <label>Concession % (bp)<input aria-label="Concession basis points" inputMode="numeric" size={6} value={form.concessionBp} onChange={(e) => setForm({ ...form, concessionBp: e.target.value })} /></label>
            </div>
            <label style={{ display: "flex", flexDirection: "column", fontSize: 12, color: "var(--muted)" }}>
              Your buyer offers (one per line, lowest first)
              <textarea aria-label="Buyer offers" rows={4} style={{ marginTop: 4, fontFamily: "var(--font-mono)" }} value={form.offers} onChange={(e) => setForm({ ...form, offers: e.target.value })} />
            </label>
            <div className="toolbar" style={{ marginTop: 12 }}>
              <button onClick={run} disabled={busy}>{busy ? "Simulating…" : "Run simulation"}</button>
            </div>
          </div>

          {out ? (
            <>
              <div className="cards">
                <div className="card"><div className="k">Result</div><div className="v mono">{out.result}</div></div>
                <div className="card"><div className="k">Score</div><div className="v mono">{out.score}</div></div>
                {out.settled_minor != null ? (
                  <div className="card"><div className="k">Settled at</div><div className="v mono">{fmtMinor(out.settled_minor, form.currency)}</div></div>
                ) : null}
              </div>
              {out.reason ? <div className="banner" role="status">{out.reason}</div> : null}
              <h3>Rounds</h3>
              <DataTable caption="Negotiation rounds" rows={out.rounds} rowKey={(r) => String(r.round)} columns={roundCols} empty={<Empty title="No rounds" />} />
            </>
          ) : (
            <Empty title="No simulation yet" hint="Describe a price situation and run it." />
          )}
    </Shell>
  );
}
