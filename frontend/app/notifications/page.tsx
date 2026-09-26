"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Shell from "../../components/Shell";
import { Badge, DataTable, Empty, ErrorBox, LiveRegion, Skeleton, useBoot, type Column } from "../../components/ui";
import { api } from "../../lib/api";

type Notif = { id: string; kind: string; title: string; body: string; link: string; read: boolean; createdAt: string };

const POLL_MS = 30000;

export default function Notifications() {
  const [rows, setRows] = useState<Notif[]>([]);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [busy, setBusy] = useState("");
  // Ref holds the latest filter for the poller without re-subscribing every click.
  const filterRef = useRef(filter);
  useEffect(() => {
    filterRef.current = filter;
  }, [filter]);

  const load = useCallback(async (unread: boolean) => {
    setRows((await api<Notif[]>(`/api/v1/notifications?limit=25${unread ? "&unread=true" : ""}`)).data || []);
  }, []);

  const { state, error } = useBoot(() => load(false));
  const shownErr = err || error;

  // The filter is applied by re-querying from the button handler, not by an
  // effect: the unread predicate lives on the server (read state is
  // per-recipient), so a client-side hide would be a lie.
  function setFilterAndLoad(next: "all" | "unread") {
    setFilter(next);
    load(next === "unread").catch(() => setErr("Could not refresh the alert feed."));
  }

  // Honest polling. The page previously claimed "Polls every 30s" in its
  // subtitle while loading exactly once — the claim was a lie, so this now
  // actually polls, and a new alert appears without a manual refresh.
  useEffect(() => {
    if (state !== "ok") return;
    const id = setInterval(() => {
      load(filterRef.current === "unread").catch(() => {
        // A failed refresh keeps the last good list rather than blanking it.
      });
    }, POLL_MS);
    return () => clearInterval(id);
  }, [state, load]);

  async function mark(id: string) {
    setBusy(id); setErr("");
    try {
      await api(`/api/v1/notifications/${id}/read`, { method: "POST" });
      // Read state is per-recipient, so this only clears it for the current user.
      setRows((rs) => rs.map((r) => (r.id === id ? { ...r, read: true } : r)));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Mark failed");
    } finally {
      setBusy("");
    }
  }

  const columns: Column<Notif>[] = [
    { key: "kind", header: "Kind", render: (n) => <Badge tone={n.read ? undefined : "info"}>{n.kind}</Badge> },
    {
      key: "title", header: "Title", render: (n) => (
        <>
          {n.title}
          {n.body ? <div style={{ color: "var(--muted)", fontSize: 12 }}>{n.body}</div> : null}
        </>
      ),
    },
    { key: "when", header: "When", render: (n) => <span className="mono" style={{ fontSize: 12 }}>{n.createdAt ? new Date(n.createdAt).toLocaleString() : "—"}</span> },
    {
      key: "act", header: "", render: (n) =>
        n.read ? (
          <span style={{ color: "var(--muted)", fontSize: 12 }}>read</span>
        ) : (
          <button className="ghost" onClick={() => mark(n.id)} disabled={busy !== ""}>
            {busy === n.id ? "…" : "Mark read"}
          </button>
        ),
    },
  ];

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Alerts</h1>
          <p>Awards, approvals, expiries and anomalies — newest first, refreshed every 30 seconds. Read state is yours alone.</p>
        </div>
      </div>
      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}</LiveRegion>

      <div className="toolbar">
        <button className="ghost" onClick={() => setFilterAndLoad("all")} aria-pressed={filter === "all"}>All</button>
        <button className="ghost" onClick={() => setFilterAndLoad("unread")} aria-pressed={filter === "unread"}>Unread only</button>
      </div>

      {state === "loading" ? <Skeleton rows={4} label="Loading alerts" />
        : state === "signin" ? <Empty title="Sign-in required" />
        : (
        <DataTable
          caption="Notification feed"
          rows={rows}
          rowKey={(n) => n.id}
          columns={columns}
          empty={<Empty title={filter === "unread" ? "All caught up" : "No alerts yet"} hint="Awards, approvals and expiries appear here automatically." />}
        />
      )}
    </Shell>
  );
}
