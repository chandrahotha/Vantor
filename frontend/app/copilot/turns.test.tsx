import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Copilot from "./page";

/**
 * VNT-037: the copilot's turn identity.
 *
 * Every turn used to be appended with the literal ids `"you"` and `"ai"`. That
 * was not only duplicate React keys. `patchTurn("ai", …)` matched *every* turn
 * carrying that id, so asking a second question streamed the new answer into the
 * first question's turn as well — silently overwriting a completed,
 * evidence-cited answer. On a screen whose entire claim is that answers are
 * reviewable, that is the worst possible place for it to happen.
 *
 * These tests drive the real component with a stubbed stream, because the bug is
 * in the wiring between turn creation, the stream callbacks and the render, and
 * a unit test of the id generator alone would not have caught it.
 */

const streamCalls: Array<{ prompt: string }> = [];
let streamCount = 0;

// Resolved from this file's location: app/copilot/ -> frontend/lib/api, which is
// the same module the page imports as "../../lib/api".
vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    api: vi.fn(async (path: string) => {
      if (path.includes("/ai/providers")) {
        return {
          data: {
            active: "disabled",
            available: [{ name: "disabled", configured: true, needsKey: false }],
          },
        };
      }
      return { data: null };
    }),
  };
});

vi.mock("../../lib/ai", () => ({
  aiStream: (
    _req: { prompt: string },
    handlers: {
      signal?: AbortSignal;
      onDelta: (d: string) => void;
      onEvidence: (ev: unknown) => void;
    },
  ) =>
    (async () => {
      streamCalls.push(_req);
      // Each call answers with distinguishable text, so a test can tell whether
      // the *first* answer was corrupted by the *second* stream. A stream that
      // always said the same thing would let that bug pass.
      streamCount += 1;
      const n = streamCount;
      handlers.onDelta(`ANSWER-${n} `);
      handlers.onEvidence({ provider: "disabled", model: "det", confidence: 0.9, evidence: [] });
      await new Promise((r) => setTimeout(r, 0));
      return handlers;
    })(),
}));

/** The app is OIDC-gated; render the signed-in state directly. */
vi.mock("../../components/ui", async () => {
  const actual = await vi.importActual<typeof import("../../components/ui")>(
    "../../components/ui",
  );
  return {
    ...actual,
    useBoot: () => ({ state: "ok" as const, error: undefined }),
  };
});

beforeEach(() => {
  streamCalls.length = 0;
  streamCount = 0;
  localStorage.clear();
});

async function ask(text: string) {
  const user = userEvent.setup();
  // The input's accessible name comes from the wrapping <label> ("Question"),
  // and the submit button reads "Send".
  await user.type(screen.getByRole("textbox", { name: /question/i }), text);
  await user.click(screen.getByRole("button", { name: /^send$/i }));
  return user;
}

describe("copilot turn identity", () => {
  it("gives every turn a unique id", async () => {
    render(<Copilot />);
    await waitFor(() => expect(screen.getByLabelText("Conversation")).toBeInTheDocument());
    await ask("first question");
    await waitFor(() => expect(screen.getByText(/ANSWER-1/)).toBeInTheDocument());
    await ask("second question");
    await waitFor(() => expect(streamCalls).toHaveLength(2));

    const log = screen.getByLabelText("Conversation");
    // Every rendered turn is a distinct element; duplicate keys would make
    // React reuse the first node and drop the second from the DOM.
    const borders = log.querySelectorAll('div[style*="border-left"]');
    expect(borders.length).toBe(4); // two questions, two answers
  });

  it("streams into the turn that was just created, not an earlier one", async () => {
    render(<Copilot />);
    await waitFor(() => expect(screen.getByLabelText("Conversation")).toBeInTheDocument());
    await ask("first question");
    await waitFor(() => expect(screen.getByText(/ANSWER-1/)).toBeInTheDocument());

    // The first answer must survive a second exchange, showing *its own* text.
    // Before the fix both answers shared the id "ai", so `patchTurn("ai")` wrote
    // the second stream's text into the first answer's turn as well and the
    // first answer silently became "ANSWER-2".
    await ask("second question");
    await waitFor(() => expect(streamCalls).toHaveLength(2));

    const log = screen.getByLabelText("Conversation");
    const rendered = log.textContent || "";
    expect(rendered, "the first answer was overwritten by the second stream")
      .toContain("ANSWER-1");
    expect(rendered, "the second answer was never written").toContain("ANSWER-2");
    // Exactly one of each: if the ids still collided there would be two copies
    // of the second answer and none of the first.
    expect((rendered.match(/ANSWER-1/g) || []).length).toBe(1);
    expect((rendered.match(/ANSWER-2/g) || []).length).toBe(1);
  });

  it("keeps both prompts visible", async () => {
    render(<Copilot />);
    await waitFor(() => expect(screen.getByLabelText("Conversation")).toBeInTheDocument());
    await ask("what is our leakage?");
    await waitFor(() => expect(screen.getByText("what is our leakage?")).toBeInTheDocument());
    await ask("and maverick spend?");
    await waitFor(() => expect(screen.getByText("and maverick spend?")).toBeInTheDocument());
  });
});
