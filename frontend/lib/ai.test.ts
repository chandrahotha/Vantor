import { describe, expect, it, vi, beforeEach } from "vitest";
import { takeFrames, aiStream, type StreamEvidence } from "./ai";
import { ApiError } from "./api";

/**
 * The SSE parser is the only place token deltas reach the screen.
 *
 * Three real defects lived here: an unguarded `JSON.parse` (one bad frame
 * destroyed a complete answer), no abort on unmount (leaked connection plus a
 * setState after unmount), and a stream that ended without its evidence frame
 * being treated as a finished answer.
 */

vi.mock("./auth", () => ({ keycloak: () => ({ token: "test-token" }) }));

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
}

function mockStream(res: Response) {
  const fn = vi.fn().mockResolvedValue(res);
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("takeFrames — SSE buffer splitting", () => {
  it("returns only complete frames and keeps the partial tail", () => {
    const { frames, rest } = takeFrames('data: {"delta":"a"}\n\ndata: {"delta":"b"}\n\ndata: {"del');
    expect(frames).toEqual(['{"delta":"a"}', '{"delta":"b"}']);
    expect(rest).toBe('data: {"del');
  });

  it("collects every data line of a multi-line frame", () => {
    // A frame with two `data:` lines used to lose the second one entirely.
    const { frames } = takeFrames("data: one\ndata: two\n\n");
    expect(frames).toEqual(["one", "two"]);
  });

  it("ignores non-data lines (comments, keep-alives)", () => {
    const { frames } = takeFrames(": keep-alive\n\ndata: real\n\n");
    expect(frames).toEqual(["real"]);
  });

  it("handles a frame boundary that lands mid-token", () => {
    const first = takeFrames('data: {"delta":"hel');
    expect(first.frames).toEqual([]);
    const second = takeFrames(first.rest + 'lo"}\n\n');
    expect(second.frames).toEqual(['{"delta":"hello"}']);
  });
});

describe("aiStream — relaying the provider envelope", () => {
  it("concatenates deltas in order and emits the evidence frame once", async () => {
    mockStream(new Response(streamOf([
      'data: {"delta":"hel","streamed":true}\n\n',
      'data: {"delta":"lo ","streamed":true}\n\n',
      'data: {"delta":"supplier","streamed":true}\n\n',
      'data: [EVIDENCE] {"confidence":0.55,"provider":"ollama","model":"llama3.1:8b","evidence":[{"resource":"supplier","id":"s1"}],"notes":[],"requires_human_review":true,"requestId":"r1","streamed":true}\n\n',
    ]), { status: 200, headers: { "Content-Type": "text/event-stream" } }));

    let acc = "";
    const seen: StreamEvidence[] = [];
    await aiStream({ prompt: "hi" }, { onDelta: (d) => { acc += d; }, onEvidence: (e) => seen.push(e) });

    expect(acc).toBe("hello supplier");
    expect(seen).toHaveLength(1);
    expect(seen[0].provider).toBe("ollama");
    expect(seen[0].model).toBe("llama3.1:8b");
    expect(seen[0].requires_human_review).toBe(true);
    expect(seen[0].evidence).toEqual([{ resource: "supplier", id: "s1" }]);
  });

  it("surfaces an in-band provider error instead of pretending to answer", async () => {
    mockStream(new Response(streamOf([
      'data: {"error":"no API key for openai","provider":"openai","streamed":true}\n\n',
    ]), { status: 200, headers: { "Content-Type": "text/event-stream" } }));

    await expect(aiStream({ prompt: "hi" }, { onDelta: () => {}, onEvidence: () => {} }))
      .rejects.toThrow(/openai: no API key for openai/);
  });

  it("keeps a complete answer when one frame is unparseable", async () => {
    // Regression: an unguarded JSON.parse threw into the outer catch and the
    // user saw "No answer produced" instead of the answer they had.
    mockStream(new Response(streamOf([
      'data: {"delta":"one "}\n\n',
      "data: {not json at all}\n\n",
      'data: {"delta":"two"}\n\n',
      'data: [EVIDENCE] {"confidence":0.55,"provider":"ollama","evidence":[],"notes":[],"requires_human_review":true,"requestId":"r1","streamed":true}\n\n',
    ]), { status: 200, headers: { "Content-Type": "text/event-stream" } }));

    let acc = "";
    await aiStream({ prompt: "hi" }, { onDelta: (d) => { acc += d; }, onEvidence: () => {} });
    expect(acc).toBe("one two");
  });

  it("refuses to call an answer complete when the evidence frame never arrived", async () => {
    mockStream(new Response(streamOf(['data: {"delta":"half an answer"}\n\n']),
      { status: 200, headers: { "Content-Type": "text/event-stream" } }));

    await expect(aiStream({ prompt: "hi" }, { onDelta: () => {}, onEvidence: () => {} }))
      .rejects.toThrow(/ended before its evidence/);
  });

  it("turns an HTTP failure into readable copy, not a bare status", async () => {
    mockStream(new Response("nope", { status: 401 }));
    const p = aiStream({ prompt: "hi" }, { onDelta: () => {}, onEvidence: () => {} });
    await expect(p).rejects.toBeInstanceOf(ApiError);
    await expect(p).rejects.toThrow(/Session expired/);
  });

  it("sends a per-request BYOK key as a header, never in the body", async () => {
    const fn = mockStream(new Response(streamOf([
      'data: [EVIDENCE] {"confidence":0,"provider":"openai","evidence":[],"notes":[],"requires_human_review":true,"requestId":"r1","streamed":true}\n\n',
    ]), { status: 200, headers: { "Content-Type": "text/event-stream" } }));

    await aiStream({ prompt: "hi", provider: "openai", model: "gpt-4o-mini", providerKey: "sk-secret" },
      { onDelta: () => {}, onEvidence: () => {} });

    const init = fn.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers["X-Vantor-Provider-Key"]).toBe("sk-secret");
    expect(headers.Authorization).toBe("Bearer test-token");
    // The key must not be duplicated into the request body.
    expect(String(init.body)).not.toContain("sk-secret");
    expect(JSON.parse(String(init.body))).toEqual({ prompt: "hi", provider: "openai", model: "gpt-4o-mini" });
  });

  it("stops cleanly when the caller aborts", async () => {
    const enc = new TextEncoder();
    const controller = new AbortController();
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(enc.encode('data: {"delta":"a"}\n\n'));
        // never closes: the abort must be what ends the loop
      },
    });
    mockStream(new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }));

    const seen: string[] = [];
    const p = aiStream({ prompt: "hi" }, { onDelta: (d) => seen.push(d), onEvidence: () => {}, signal: controller.signal });
    await new Promise((r) => setTimeout(r, 10));
    controller.abort();
    await expect(p).resolves.toBeUndefined();
    expect(seen).toEqual(["a"]);
  });
});
