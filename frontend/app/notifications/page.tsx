"use client";
import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { Badge, Empty, ErrorBox } from "../../components/ui";
import { api } from "../../lib/api";
import { keycloak, parseSession, keepFresh, setSession } from "../../lib/auth";
import { setTokenGetter, setRefreshFn } from "../../lib/api";

type Notif = { id: string; kind: string; title: string; body: string; link: string; read: boolean; createdAt: string };

export default function Notifications() {
  const [rows, setRows] = useState<Notif[]>([]);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "unread">("all");

  async function load(unread: boolean) {
    setLoading(true);
    try {
      setRows((await api<Notif[]>(`/api/v1/notifications?limit=25${unread ? "&unread=true" : ""}`)).data || []);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Load failed"); }
    setLoading(false);
  }

  useEffect(() => {
    let stop = () => {};
    const kc = keycloak();
    kc.init({ onLoad: "login-required", pkceMethod: "S256", checkLoginIframe: false }).then(async (ok) => {
      if (!ok) { setErr("Sign-in required."); setLoading(false); return; }
      stop = keepFresh(kc, () => setErr("Session expired - please sign in again."));
      const s = parseSession(kc);
      if (!s?.tenant) { setErr("Token carries no tenant."); setLoading(false); return; }
      setSession({ token: s.token, name: s.name, tenant: s.tenant, roles: s.roles });
      setTokenGetter(() => keycloak().token);
      setRefreshFn(async () => { try { await keycloak().updateToken(60); return true; } catch { return false; } });
      await load(false);
    }).catch(() => { setErr("Keycloak unreachable."); setLoading(false); });
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function mark(id: string) {
    try {
      await api(`/api/v1/notifications/${id}/read`, { method: "POST" });
      setRows((rs) => rs.map((r) => (r.id === id ? { ...r, read: true } : r)));
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Mark failed"); }
  }

  return (
    <Shell>
      <div className="pagehead"><div><h1>Alerts</h1><p>Awards, approvals, expiries, anomalies — newest first. Polls every 30s.</p></div></div>
      {err ? <ErrorBox message={err} /> : null}
      <div className="toolbar">
        <button className="ghost" onClick={() => { setFilter("all"); load(false); }}>All</button>
        <button className="ghost" onClick={() => { setFilter("unread"); load(true); }}>Unread only</button>
      </div>
      {loading ? <div className="skel" /> : rows.length === 0 ? <Empty title={filter === "unread" ? "All caught up" : "No alerts yet"} /> : (
        <table className="grid"><thead><tr><th>Kind</th><th>Title</th><th>When</th><th></th></tr></thead>
          <tbody>{rows.map((n) => (<tr key={n.id} style={n.read ? undefined : { background: "#eff6ff" }}>
            <td><Badge tone={n.read ? undefined : "info"}>{n.kind}</Badge></td>
            <td>{n.title}{n.body ? <div style={{ color: "var(--muted)", fontSize: 12 }}>{n.body}</div> : null}</td>
            <td className="mono" style={{ fontSize: 12 }}>{n.createdAt ? new Date(n.createdAt).toLocaleString() : "—"}</td>
            <td>{n.read ? null : <button className="ghost" onClick={() => mark(n.id)}>Mark read</button>}</td></tr>))}</tbody></table>
      )}
    </Shell>
  );
}
