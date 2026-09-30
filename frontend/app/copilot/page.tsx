"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Shell from "../../components/Shell";
import Link from "next/link";
import { AuthScreen, Badge, Empty, ErrorBox, LiveRegion, useBoot } from "../../components/ui";
import { api } from "../../lib/api";
import { aiStream, type ProviderList, type StreamEvidence, type EvidenceRef } from "../../lib/ai";

type Turn = {
  id: string;
  role: "you" | "ai" | "system";
  text: string;
  provider?: string;
  model?: string;
  confidence?: number | null;
  evidence?: EvidenceRef[];
  notes?: string[];
  requiresHumanReview?: boolean;
  streamed?: boolean;
};

const SUGGESTIONS = [
  "Which suppliers are single-sourced for this category?",
  "Summarise our open price anomalies.",
  "Explain how three-way match decides an invoice.",
];

/** One citation line. The API returns plain objects, so raw JSON was unreadable. */
function citation(e: EvidenceRef): string {
  const ref = e.resource ?? e.type ?? e.kind;
  const id = e.id ?? e.resourceId ?? e.poId ?? e.invoiceId ?? e.rfqId ?? e.supplierId;
  if (ref && id) return `${ref} ${id}`;
  if (id) return String(id);
  if (ref) return String(ref);
  const first = Object.entries(e)[0];
  return first ? `${first[0]}: ${String(first[1])}` : "citation";
}

export default function Copilot() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [providers, setProviders] = useState<ProviderList | null>(null);
  const [provider, setProvider] = useState("");
  // VNT-038. The provider picker has always offered options labelled "needs your
  // API key", with no way to supply one — so picking one was a dead end that
  // failed at request time with an upstream error the user could not act on. The
  // backend has accepted a per-request key all along (`X-Vantor-Provider-Key`);
  // only the entry flow was missing.
  //
  // The key lives in component state and nowhere else: not localStorage, not
  // sessionStorage, not the server. It goes out as a header on the one request it
  // applies to and is then forgotten, because a BYOK secret persisted in a browser
  // is a credential at rest on a shared machine.
  const [providerKey, setProviderKey] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  // Monotonic turn counter and the id of the turn currently streaming. VNT-037:
  // turn ids must be unique, and the stream must address one specific turn
  // rather than "whatever turn happens to have the ai role".
  const seq = useRef(0);
  const activeAiRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    setProviders((await api<ProviderList>("/api/v1/ai/providers")).data);
  }, []);

  const { state, error, reload } = useBoot(load);
  const shownErr = err || error;

  // The provider that needs a key typed in: one that requires a key and has none
  // on the server. A provider the server is already configured for never shows
  // the field, because typing a key there would override a working deployment
  // key for no reason.
  const selected = providers?.available.find((p) => p.name === provider);
  const needsOwnKey = !!(selected?.needsKey && !selected.configured);

  // Never leave an open stream behind: navigating away mid-answer used to leave
  // the connection running and set state on an unmounted component.
  useEffect(() => () => abortRef.current?.abort(), []);

  function patchTurn(id: string, patch: Partial<Turn>) {
    setTurns((t) => t.map((x) => (x.id === id ? { ...x, ...patch } : x)));
  }

  async function send(prompt?: string) {
    const text = (prompt ?? q).trim();
    if (!text || busy) return;
    // Refuse before the request rather than letting the provider fail: an
    // upstream 401 for a missing key reads as "the app is broken" and gives the
    // user nothing to act on.
    const chosen = providers?.available.find((p) => p.name === provider);
    if (chosen?.needsKey && !chosen.configured && !providerKey.trim()) {
      setErr(`${chosen.name} needs an API key. Enter one below, or choose another provider.`);
      return;
    }
    setQ("");
    setBusy(true);
    setErr("");
    // VNT-037. These two ids used to be the literals "you" and "ai", on every
    // turn. That produced two distinct bugs, and the second is the serious one:
    //
    //   * duplicate React keys across turns, which is a reconciliation warning
    //     and undefined behaviour for anything stateful inside a turn; and
    //   * `patchTurn("ai", ...)` matched *every* turn with that id, so asking a
    //     second question streamed the new answer into the first answer's turn as
    //     well. The earlier answer was silently overwritten, on a screen whose
    //     entire claim is that answers are evidence-cited and reviewable.
    //
    // A counter rather than a random id: it is stable for the life of the
    // conversation, is readable in a DOM inspector, and cannot collide.
    const youId = `you-${++seq.current}`;
    const aiId = `ai-${seq.current}`;
    activeAiRef.current = aiId;
    setTurns((t) => [
      ...t,
      { id: youId, role: "you", text },
      { id: aiId, role: "ai", text: "" },
    ]);
    const controller = new AbortController();
    abortRef.current = controller;
    let acc = "";
    try {
      await aiStream(
        { prompt: text, provider: provider || undefined, providerKey: providerKey.trim() || undefined },
        {
          signal: controller.signal,
          onDelta: (d) => {
            acc += d;
            patchTurn(aiId, { text: acc });
          },
          onEvidence: (ev: StreamEvidence) => patchTurn(aiId, {
            provider: ev.provider,
            model: ev.model,
            confidence: ev.confidence,
            evidence: ev.evidence,
            notes: ev.notes,
            requiresHumanReview: ev.requires_human_review,
            streamed: ev.streamed,
          }),
        },
      );
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      const msg = e instanceof Error ? e.message : "Copilot unavailable";
      setErr(msg);
      patchTurn(aiId, { role: "system", text: msg });
    } finally {
      abortRef.current = null;
      activeAiRef.current = null;
      setBusy(false);
    }
  }

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Copilot</h1>
          <p>
            Ask a question about your own procurement data. Every answer cites the records it was drawn from.
          </p>
        </div>
      </div>

      <LiveRegion>{shownErr ? <ErrorBox message={shownErr} /> : null}</LiveRegion>

      <>
          {providers ? (
            <div className="toolbar" style={{ alignItems: "center", gap: 8 }}>
              <span style={{ color: "var(--muted)", fontSize: 12 }}>Active provider:</span>{" "}
              <strong style={{ fontSize: 12 }}>{providers.active}</strong>
              <label style={{ fontSize: 12 }} htmlFor="copilot-provider">Ask using</label>
              <select
                id="copilot-provider"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                style={{ fontSize: 12 }}
              >
                <option value="">Server default ({providers.active})</option>
                {providers.available.map((p) => (
                  <option key={p.name} value={p.name} disabled={!p.configured && !p.needsKey}>
                    {p.name}
                    {p.needsKey && !p.configured ? " — needs your API key" : ""}
                    {!p.configured && !p.needsKey ? " — not configured" : ""}
                  </option>
                ))}
              </select>
              {needsOwnKey ? (
                <>
                  <label style={{ fontSize: 12 }} htmlFor="copilot-provider-key">
                    {selected?.name} API key
                  </label>
                  <input
                    id="copilot-provider-key"
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={providerKey}
                    onChange={(e) => setProviderKey(e.target.value)}
                    placeholder="sk-…"
                    style={{ fontSize: 12, minWidth: 220 }}
                  />
                  <button
                    type="button"
                    className="ghost"
                    style={{ fontSize: 12, padding: "4px 10px" }}
                    onClick={() => setProviderKey("")}
                    disabled={!providerKey}
                  >
                    Clear key
                  </button>
                </>
              ) : null}
            </div>
          ) : null}
          {needsOwnKey ? (
            <p style={{ color: "var(--muted)", fontSize: 12, margin: "-4px 0 10px" }}>
              Your key is sent only with the next request. It is not stored in this
              browser and not saved on the server, so you will be asked again after a
              reload. The server&apos;s own key for {selected?.name} is used instead if
              one is configured.
            </p>
          ) : null}

          <div
            role="log"
            aria-label="Conversation"
            aria-busy={busy}
            className="panel"
            style={{ minHeight: 180, marginTop: 12 }}
          >
            {turns.length === 0 ? (
              <Empty title="Ask something" hint="Try one of the suggestions, or write your own question." />
            ) : (
              turns.map((t, i) => (
                <div
                  key={t.id}
                  style={{
                    marginBottom: 14,
                    borderLeft: `3px solid ${t.role === "you" ? "var(--primary)" : t.role === "system" ? "var(--warn)" : "var(--line)"}`,
                    paddingLeft: 12,
                  }}
                >
                  <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--muted)" }}>
                    {t.role === "you" ? "You" : t.role === "system" ? "Not answered" : "Copilot"}
                    {t.provider ? <> · <Badge tone="info">{t.provider}</Badge></> : null}
                    {t.model ? <> <span className="mono">{t.model}</span></> : null}
                    {t.confidence != null ? <> · confidence {Math.round(t.confidence * 100)}%</> : null}
                    {t.requiresHumanReview ? <> · <Badge tone="warn">advisory</Badge></> : null}
                  </div>
                  {/* The pending-answer marker goes on the turn that is actually
                      streaming, not on every empty AI turn. Keying it off
                      `role === "ai"` meant a second question put a "…" in the
                      first question's completed answer. Indexed off the end of
                      the list rather than a ref, because a ref does not
                      re-render. */}
                  <div style={{ marginTop: 4, whiteSpace: "pre-wrap" }}>
                    {t.text || (busy && t.role === "ai" && i === turns.length - 1 ? "…" : "")}
                  </div>
                  {t.streamed === false && t.role === "ai" ? (
                    <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                      This environment is running in deterministic mode — the response is complete
                      when it renders, not token-streamed.
                    </div>
                  ) : null}
                  {t.notes && t.notes.length > 0 ? (
                    <ul style={{ fontSize: 12, color: "var(--warn)", marginTop: 6 }}>
                      {t.notes.map((n, i) => <li key={i}>{n}</li>)}
                    </ul>
                  ) : null}
                  {t.evidence && t.evidence.length > 0 ? (
                    <details style={{ fontSize: 12, marginTop: 6 }}>
                      <summary style={{ cursor: "pointer", color: "var(--muted)" }}>
                        {t.evidence.length} cited record{t.evidence.length === 1 ? "" : "s"}
                      </summary>
                      <ul style={{ color: "var(--muted)" }}>
                        {t.evidence.map((e, j) => (
                          <li key={j}><span className="mono">{citation(e)}</span></li>
                        ))}
                      </ul>
                    </details>
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
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Which supplier is single-sourced for fasteners?"
                disabled={busy}
              />
            </label>
            <button type="submit" disabled={busy || !q.trim()}>{busy ? "Thinking…" : "Send"}</button>
          </form>

          {/* The full approval workbench used to be mounted here, below the chat
              log. Since it became a route of its own it was rendered in two
              places at once: two independent `useBoot` gates, two polls of the
              same queue, and two copies of a screen that governs money, one of
              them filed under the AI assistant. The queue lives at /approvals;
              this is the pointer to it. */}
          <div className="info-callout" style={{ marginTop: 20 }}>
            <span className="info-callout-icon" aria-hidden="true">✓</span>
            <span>
              The copilot can only advise. Anything it files for a decision waits in the{" "}
              <Link href="/approvals">approval queue</Link>, where a person approves or rejects it
              with a written reason.
            </span>
          </div>
        </>
    </Shell>
  );
}
