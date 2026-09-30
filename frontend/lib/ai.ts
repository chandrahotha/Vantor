/** AI client — typed envelope + one SSE implementation for the whole app.
 *
 *  The copilot used to hand-roll its own `fetch`, its own token read and its own
 *  error string, which is how it ended up bypassing the 401 refresh, showing raw
 *  HTTP status codes to the user, and crashing on a malformed frame. Everything
 *  AI-shaped now goes through here so it cannot drift from `api()` again.
 */
import { API_URL, ApiError, friendly } from "./api";
import { getSession } from "./auth";

/** One row from `GET /ai/providers`. Keys are never returned by the API. */
export type ProviderInfo = {
  name: string;
  /** The server can complete a request with this provider using only its own env. */
  configured: boolean;
  /** The caller must supply a BYOK key per request. */
  needsKey: boolean;
  active: boolean;
};

export type ProviderList = { active: string; available: ProviderInfo[] };

/** The non-streaming completion envelope (`POST /ai/complete`). */
export type Completion = {
  answer: string;
  confidence: number;
  evidence: EvidenceRef[];
  data_timestamp: string;
  requires_human_review: boolean;
  provider: string;
  model: string;
  notes?: string[];
};

export type EvidenceRef = Record<string, unknown> & {
  resource?: string;
  id?: string;
  [k: string]: unknown;
};

/** The terminal `[EVIDENCE]` frame of `POST /ai/stream`. */
export type StreamEvidence = {
  confidence: number | null;
  provider: string;
  model: string;
  evidence: EvidenceRef[];
  notes: string[];
  requires_human_review: boolean;
  requestId: string;
  streamed: boolean;
};

export type StreamHandlers = {
  onDelta: (text: string) => void;
  onEvidence: (evidence: StreamEvidence) => void;
  signal?: AbortSignal;
};

export type StreamRequest = {
  prompt: string;
  provider?: string;
  model?: string;
  /** Per-request BYOK key. Sent as a header, never in the body, never stored. */
  providerKey?: string;
  system?: string;
};

const EMPTY_EVIDENCE: StreamEvidence = {
  confidence: null, provider: "", model: "", evidence: [], notes: [],
  requires_human_review: true, requestId: "", streamed: false,
};

function parseJson<T>(raw: string, what: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch {
    // A single bad frame must not destroy an otherwise complete answer.
    if (typeof console !== "undefined") console.warn(`[ai] ignored unparseable ${what} frame`);
    return null;
  }
}

/** Split an SSE buffer into complete `data:` payloads. Exported for tests. */
export function takeFrames(buffer: string): { frames: string[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const frames: string[] = [];
  for (const part of parts) {
    for (const line of part.split("\n")) {
      const trimmed = line.trim();
      if (trimmed.startsWith("data:")) frames.push(trimmed.slice(5).trim());
    }
  }
  return { frames, rest };
}

/** POST /ai/stream and relay provider-side deltas as they arrive. */
export async function aiStream(req: StreamRequest, handlers: StreamHandlers): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  // The SSE route sits behind the same OIDC guard as every other endpoint. An
  // unauthenticated stream would 401 with no frames at all, and `Bearer ` (an
  // empty credential) is worse than omitting the header.
  const token = getSession()?.token;
  if (token) headers.Authorization = `Bearer ${token}`;
  if (req.providerKey) headers["X-Vantor-Provider-Key"] = req.providerKey;

  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/ai/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        prompt: req.prompt,
        ...(req.provider ? { provider: req.provider } : {}),
        ...(req.model ? { model: req.model } : {}),
        ...(req.system ? { system: req.system } : {}),
      }),
      signal: handlers.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") return;
    throw new ApiError(0, "NETWORK_ERROR", "Copilot unreachable — is the API running?", "");
  }
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, "STREAM_FAILED",
      friendly(res.status, "STREAM_FAILED", `Copilot request failed (${res.status}).`),
      res.headers.get("X-Request-ID") || "");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const signal = handlers.signal;
  // Passing `signal` to fetch() is not enough: it cancels the request, not a read
  // already in flight, so navigating away mid-answer would leave the loop
  // awaiting a chunk forever and hold the connection open. Watch the signal here
  // too and cancel the reader, which is what actually unblocks the read.
  let onAbort: (() => void) | null = null;
  if (signal) {
    onAbort = () => { void reader.cancel().catch(() => {}); };
    signal.addEventListener("abort", onAbort, { once: true });
  }

  let buffer = "";
  let sawEvidence = false;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const taken = takeFrames(buffer);
      buffer = taken.rest;
      for (const frame of taken.frames) {
        if (frame.startsWith("[EVIDENCE]")) {
          const parsed = parseJson<StreamEvidence>(frame.slice("[EVIDENCE]".length), "evidence");
          if (parsed) {
            sawEvidence = true;
            handlers.onEvidence({ ...EMPTY_EVIDENCE, ...parsed });
          }
          continue;
        }
        const parsed = parseJson<{ delta?: string; error?: string; provider?: string }>(frame, "delta");
        if (!parsed) continue;
        if (parsed.error) {
          throw new ApiError(502, "AI_PROVIDER_FAILED",
            `${parsed.provider ? `${parsed.provider}: ` : ""}${parsed.error}`, "");
        }
        if (parsed.delta) handlers.onDelta(parsed.delta);
      }
    }
  } catch (e) {
    // An abort is the caller's decision, not a failure — a cancelled read can
    // surface either as a rejection or as a clean `done`, so check both.
    if (signal?.aborted) return;
    throw e;
  } finally {
    if (onAbort && signal) signal.removeEventListener("abort", onAbort);
  }
  if (signal?.aborted) return;
  // A stream that ended without its evidence frame is not a complete answer.
  if (!sawEvidence) {
    throw new ApiError(0, "STREAM_TRUNCATED",
      "The answer stream ended before its evidence arrived — treat this as unanswered.", "");
  }
}
