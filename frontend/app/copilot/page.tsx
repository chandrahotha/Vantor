"use client";
import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { Badge, ErrorBox } from "../../components/ui";
import { api } from "../../lib/api";
import { keycloak, parseSession, keepFresh, setSession } from "../../lib/auth";
import { setTokenGetter, setRefreshFn } from "../../lib/api";

type Msg = { role: "user" | "ai"; text: string; confidence?: number; provider?: string; review?: boolean };

export default function Copilot() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let stop = () => {};
    const kc = keycloak();
    kc.init({ onLoad: "login-required", pkceMethod: "S256", checkLoginIframe: false }).then((ok) => {
      if (!ok) return;
      stop = keepFresh(kc, () => setErr("Session expired - please sign in again."));
      const s = parseSession(kc);
      if (!s?.tenant) { setErr("Token carries no tenant."); return; }
      setTokenGetter(() => keycloak().token); const __s = parseSession(keycloak()); if (__s) setSession({ token: __s.token, name: __s.name, tenant: __s.tenant, roles: __s.roles }); setRefreshFn(async () => { try { await keycloak().updateToken(60); return true; } catch { return false; } });
    }).catch(() => setErr("Keycloak unreachable."));
    return () => stop();
  }, []);

  async function ask() {
    if (!input.trim() || busy) return;
    const q = input.trim();
    setInput(""); setBusy(true); setErr("");
    setMsgs((m) => [...m, { role: "user", text: q }]);
    try {
      const r = await api<{ answer: string; confidence: number; provider: string; requires_human_review: boolean }>("/api/v1/ai/complete", {
        method: "POST", body: JSON.stringify({ prompt: q }),
      });
      setMsgs((m) => [...m, { role: "ai", text: r.data.answer, confidence: r.data.confidence, provider: r.data.provider, review: r.data.requires_human_review }]);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Copilot failed";
      // Surface provider failures explicitly (never fake an answer).
      setMsgs((m) => [...m, { role: "ai", text: `NEEDS VERIFICATION — ${msg}` }]);
    }
    setBusy(false);
  }

  return (
    <Shell>
      <div className="pagehead"><div><h1>Procurement copilot</h1><p>Evidence-first answers — every reply needs human review.</p></div></div>
      {err ? <ErrorBox message={err} /> : null}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 12 }}>
        {msgs.map((m, i) => (
          <div key={i} className="card" style={{ borderLeft: `3px solid ${m.role === "user" ? "var(--primary)" : "var(--emerald)"}` }}>
            <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>
            {m.role === "ai" ? (
              <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
                <Badge tone="info">{m.provider || "ai"}</Badge>
                {m.confidence !== undefined ? <span className="mono" style={{ fontSize: 12 }}>confidence {(m.confidence * 100).toFixed(0)}%</span> : null}
                {m.review ? <Badge tone="warn">REQUIRES HUMAN REVIEW</Badge> : null}
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <div className="toolbar">
        <input type="text" style={{ flex: 1 }} placeholder="Ask about suppliers, RFQs, spend…" value={input}
          onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") ask(); }} aria-label="Ask copilot" />
        <button onClick={ask} disabled={busy}>{busy ? "Thinking…" : "Ask"}</button>
      </div>
    </Shell>
  );
}


