"use client";
import { useCallback, useState } from "react";
import { Badge, DataTable, Empty, ErrorBox, LiveRegion, Skeleton, useBoot, type Column } from "../../components/ui";
import { ApiError, api, newIdemKey } from "../../lib/api";

/** One row of `GET /approvals`. */
export type Approval = {
  id: string;
  resource: string;
  resourceId: string;
  status: string;
  tier: string;
  requestedBy: string;
  decidedBy: string;
  reason: string;
  requiresHumanReview: boolean;
  createdAt: string;
};

const TONE: Record<string, "ok" | "warn" | "bad" | "info"> = {
  requested: "warn", approved: "ok", rejected: "bad",
};

export default function Approvals() {
  const [rows, setRows] = useState<Approval[]>([]);
  const [busyId, setBusyId] = useState("");
  const [err, setErr] = useState("");
  const [notice, setNotice] = useState("");
  // Rejection needs a written reason (the API refuses one without it), so the
  // reason box is per-row and only shown while a rejection is being composed.
  const [rejecting, setRejecting] = useState("");
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    setErr("");
    try {
      const r = await api<Approval[]>("/api/v1/approvals?status=requested&limit=25");
      setRows(r.data ?? []);
    } catch (e) {
      // 403 simply means this caller is not an approver — not a failure worth
      // shouting about on a copilot page.
      if (e instanceof ApiError && e.status === 403) setRows([]);
      else setErr(e instanceof Error ? e.message : "Approval queue unavailable");
    }
  }, []);

  // `useBoot` owns the first invocation and the auth gate; a plain effect that
  // calls setState directly is exactly what the react-hooks lint rule blocks.
  // After a decision we call `load()` again from the handler, where it belongs.
  const { state } = useBoot(load);
  const ready = state === "ok";

  async function decide(id: string, approve: boolean) {
    if (!approve && !reason.trim()) {
      setErr("A rejection needs a written reason.");
      return;
    }
    setBusyId(id);
    setErr("");
    setNotice("");
    try {
      const r = await api<{ id: string; status: string; resourceStatus?: string }>(
        `/api/v1/approvals/${id}/decide`,
        {
          method: "POST",
          idemKey: newIdemKey(),
          body: JSON.stringify({ approve, reason: reason.trim() }),
        },
      );
      setNotice(`Approval ${r.data.status}${r.data.resourceStatus ? ` · document is now ${r.data.resourceStatus}` : ""}.`);
      setRejecting("");
      setReason("");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Decision failed");
    } finally {
      setBusyId("");
    }
  }

  const columns: Column<Approval>[] = [
    { key: "resource", header: "Document", render: (a: Approval) => `${a.resource} ${a.resourceId.slice(0, 8)}` },
    { key: "tier", header: "Tier", render: (a: Approval) => <Badge tone="info">{a.tier}</Badge> },
    { key: "requestedBy", header: "Requested by", render: (a: Approval) => <span className="mono">{a.requestedBy}</span> },
    { key: "status", header: "Status", render: (a: Approval) => <Badge tone={TONE[a.status] ?? "info"}>{a.status}</Badge> },
    {
      key: "actions",
      header: "Decision",
      render: (a: Approval) => (
        <span className="toolbar" style={{ gap: 6 }}>
          <button className="ghost" disabled={busyId === a.id} onClick={() => decide(a.id, true)}>
            {busyId === a.id ? "Saving…" : "Approve"}
          </button>
          <button
            className="ghost"
            aria-pressed={rejecting === a.id}
            disabled={busyId === a.id}
            onClick={() => { setRejecting(rejecting === a.id ? "" : a.id); setReason(""); }}
          >
            Reject
          </button>
          {rejecting === a.id ? (
            <span className="toolbar" style={{ gap: 6 }}>
              <label className="sr-only" htmlFor={`reason-${a.id}`}>Reason for rejection</label>
              <input
                id={`reason-${a.id}`}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why is this rejected?"
                style={{ minWidth: 200 }}
              />
              <button disabled={busyId === a.id} onClick={() => decide(a.id, false)}>Confirm</button>
            </span>
          ) : null}
        </span>
      ),
    },
  ];

  return (
    <section aria-labelledby="approvals-heading" style={{ marginTop: 24 }}>
      <div className="pagehead" style={{ marginBottom: 8 }}>
        <div>
          <h2 id="approvals-heading" style={{ fontSize: 16 }}>Pending Governance & Fiscal Approvals</h2>
          <p style={{ margin: 0 }}>
            Executive authorization queue: pending requisitions, purchase orders, and expenditure threshold sign-offs governed by enterprise delegation of authority.
          </p>
        </div>
      </div>

      <LiveRegion>
        {err ? <ErrorBox message={err} /> : null}
        {notice ? <p style={{ color: "var(--ok, #0f766e)", fontSize: 13 }}>{notice}</p> : null}
      </LiveRegion>

      {state === "loading" ? <Skeleton rows={2} label="Loading approvals" /> : !ready ? (
        <p style={{ color: "var(--muted)", fontSize: 12 }}>
          Sign in with an approver role to see anything waiting on a decision.
        </p>
      ) : (
        <DataTable
          caption="Pending approvals"
          rows={rows}
          rowKey={(a) => a.id}
          columns={columns}
          empty={
            <Empty
              title="Nothing waiting on you"
              hint="Requisitions, purchase orders and copilot filings that need a decision land here."
            />
          }
        />
      )}
    </section>
  );
}
