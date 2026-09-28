"use client";
import { useCallback, useState } from "react";
import Shell from "../../components/Shell";
import { AuthScreen, DataTable, Empty, ErrorBox, LiveRegion, useBoot, type Column } from "../../components/ui";
import { api, fmtMinor, newIdemKey } from "../../lib/api";

type Round = { round: number; offer_minor: number; counter_minor: number };
type SimResult = {
  result: string;
  score: number;
  rounds: Round[];
  reason?: string;
};

export default function NegoSim() {
  const [form, setForm] = useState({ listPrice: "100000.00", walkAway: "140000.00", offers: "95000\n100000\n120000", maxRounds: "5", concessionBp: "1500" });
  const [out, setOut] = useState<SimResult | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const { state, error } = useBoot(useCallback(async () => {}, []));
  const shownErr = err || error;

  async function run() {
    setBusy(true); setErr("");
    try {
      const offers = form.offers.split(/\n+/).map((s) => s.trim()).filter(Boolean).map((v) => Math.round(Number(v) * 100));
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
    { key: "offer", header: "Your offer", numeric: true, render: (x) => fmtMinor(x.offer_minor, "INR") },
    { key: "counter", header: "Supplier counter", numeric: true, render: (x) => fmtMinor(x.counter_minor, "INR") },
  ];

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Negotiation simulator</h1>
          <p>Strategic supplier negotiation workbench: counter-offer modeling, concession ladders, supplier margin analysis, and target price optimization.</p>
        </div>
      </div>
      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}</LiveRegion>

      {state !== "ok" ? <AuthScreen state={state} error={error} /> : (
        <>
          <div className="panel">
            <div className="toolbar">
              <label>List price<input aria-label="List price" inputMode="decimal" value={form.listPrice} onChange={(e) => setForm({ ...form, listPrice: e.target.value })} /></label>
              <label>Walk-away<input aria-label="Walk-away price" inputMode="decimal" value={form.walkAway} onChange={(e) => setForm({ ...form, walkAway: e.target.value })} /></label>
              <label>Max rounds<input aria-label="Max rounds" inputMode="numeric" size={4} value={form.maxRounds} onChange={(e) => setForm({ ...form, maxRounds: e.target.value })} /></label>
              <label>Concession % (bp)<input aria-label="Concession basis points" inputMode="numeric" size={6} value={form.concessionBp} onChange={(e) => setForm({ ...form, concessionBp: e.target.value })} /></label>
            </div>
            <label style={{ display: "flex", flexDirection: "column", fontSize: 12, color: "var(--muted)" }}>
              Your offers, one per line
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
              </div>
              {out.reason ? <div className="banner" role="status">{out.reason}</div> : null}
              <h3>Rounds</h3>
              <DataTable caption="Negotiation rounds" rows={out.rounds} rowKey={(r) => String(r.round)} columns={roundCols} empty={<Empty title="No rounds" />} />
            </>
          ) : (
            <Empty title="No simulation yet" hint="Describe a price situation and run it." />
          )}
        </>
      )}
    </Shell>
  );
}
