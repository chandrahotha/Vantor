"use client";
import { useCallback, useState } from "react";
import Shell from "../../components/Shell";
import { Badge, Empty, ErrorBox, LiveRegion, Skeleton, useBoot } from "../../components/ui";
import { API_URL, api } from "../../lib/api";
import { keycloak } from "../../lib/auth";

type Turn = { role: "you" | "ai" | "system"; text: string; provider?: string; confidence?: number | null; evidence?: unknown[]; streamed?: boolean };

const SUGGESTIONS = [
  "Which suppliers are single-sourced for this category?",
  "Summarise our open price anomalies.",
  "Explain how three-way match decides an invoice.",
];

export default function Copilot() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [providers, setProviders] = useState<{ active: string; available: { name: string; configured: boolean }[] } | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setProviders((await api<{ active: string; available: { name: string; configured: boolean }[] }>("/api/v1/ai/providers")).data);
  }, []);

  const { state, error } = useBoot(load);
  const shownErr = err || error;

  async function send(prompt?: string) {
    const text = (prompt ?? q).trim();
    if (!text) return;
    setQ("");
    setBusy(true); setErr("");
    setTurns((t) => [...t, { role: "you", text }]);
    const assistant: Turn = { role: "ai", text: "" };
    setTurns((t) => [...t, assistant]);
    try {
      // SSE endpoint. The server frames a *completed* provider response and marks
      // each frame `streamed: false` — surfaced in the UI rather than implied.
      const res = await fetch(`${API_URL}/api/v1/ai/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          // The SSE endpoint is behind the same OIDC guard as every other route;
          // an unauthenticated stream would 401 with no frames at all.
          Authorization: `Bearer ${keycloak().token ?? ""}`,
          Accept: "text/event-stream",
        },
        body: JSON.stringify({ prompt: text }),
      });
      if (!res.ok || !res.body) throw new Error(`Copilot request failed (${res.status}).`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let acc = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const line = frame.trim();
          if (!line.startsWith("data:")) continue;
          const payload = line.slice(5).trim();
          if (payload.startsWith("[EVIDENCE]")) {
            const ev = JSON.parse(payload.slice("[EVIDENCE]".length)) as {
              provider?: string; confidence?: number | null; evidence?: unknown[]; requires_human_review?: boolean; streamed?: boolean;
            };
            setTurns((t) => t.map((x) => (x === assistant ? { ...x, provider: ev.provider, confidence: ev.confidence, evidence: ev.evidence, streamed: ev.streamed } : x)));
          } else {
            const d = JSON.parse(payload) as { delta?: string; error?: string };
            if (d.error) throw new Error(d.error);
            acc += d.delta ?? "";
            setTurns((t) => t.map((x) => (x === assistant ? { ...x, text: acc } : x)));
          }
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Copilot unavailable";
      setErr(msg);
      setTurns((t) => t.map((x) => (x === assistant ? { role: "system", text: `No answer produced — ${msg}` } : x)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>AI copilot</h1>
          <p>
            Every answer is evidence-cited and advisory. The model never calculates: deterministic math
            stays in the deterministic engines, and nothing is committed without a human decision.
          </p>
        </div>
      </div>

      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}</LiveRegion>

      {state === "loading" ? <Skeleton rows={2} label="Loading provider status" /> : providers ? (
        <p style={{ color: "var(--muted)", fontSize: 12 }}>
          Provider: <strong>{providers.active}</strong> · available:{" "}
          {providers.available.map((p) => `${p.name}${p.configured ? "" : " (not configured)"}`).join(", ")}
        </p>
      ) : null}

      <div role="log" aria-label="Conversation" aria-live="polite" className="panel" style={{ minHeight: 180, marginTop: 12 }}>
        {turns.length === 0 ? (
          <Empty title="Ask something" hint="Try one of the suggestions, or write your own question." />
        ) : (
          turns.map((t, i) => (
            <div key={i} style={{ marginBottom: 14, borderLeft: `3px solid ${t.role === "you" ? "var(--primary)" : t.role === "system" ? "var(--warn)" : "var(--line)"}`, paddingLeft: 12 }}>
              <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--muted)" }}>
                {t.role === "you" ? "You" : t.role === "system" ? "Not answered" : "Copilot"}
                {t.provider ? <> · <Badge tone="info">{t.provider}</Badge></> : null}
                {t.confidence != null ? <> · confidence {Math.round(t.confidence * 100)}%</> : null}
              </div>
              <div style={{ marginTop: 4, whiteSpace: "pre-wrap" }}>{t.text || (busy && t.role === "ai" ? "…" : "")}</div>
              {t.streamed === false && t.role === "ai" ? (
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                  This environment is running in deterministic mode — the response is complete
                  when it renders, not token-streamed.
                </div>
              ) : null}
              {t.evidence && t.evidence.length > 0 ? (
                <ul style={{ fontSize: 12, color: "var(--muted)" }}>{t.evidence.map((e, j) => <li key={j}>{JSON.stringify(e)}</li>)}</ul>
              ) : null}
            </div>
          ))
        )}
      </div>

      <div className="toolbar">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="ghost" onClick={() => send(s)} disabled={busy}>{s}</button>
        ))}
      </div>

      <form
        className="toolbar"
        onSubmit={(e) => { e.preventDefault(); send(); }}
      >
        <label style={{ flex: 1, minWidth: 260 }}>
          Question
          <input
            aria-label="Ask the copilot"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Which supplier is single-sourced for fasteners?"
            disabled={busy}
          />
        </label>
        <button type="submit" disabled={busy || !q.trim()}>{busy ? "Thinking…" : "Send"}</button>
      </form>
      <p style={{ color: "var(--muted)", fontSize: 12 }}>
        Read-only typed tools only. High-risk actions (award, approve, contact a supplier) must be filed
        as a human-in-the-loop approval — the copilot cannot execute them.
      </p>
    </Shell>
  );
}
