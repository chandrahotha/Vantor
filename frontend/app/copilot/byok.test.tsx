import { useEffect, useState } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Copilot from "./page";

/**
 * VNT-038: the provider picker offered options labelled "needs your API key" and
 * there was no way to supply one.
 *
 * The backend has accepted a per-request key all along - both `/ai/complete` and
 * `/ai/stream` read `X-Vantor-Provider-Key`, header winning over body - so this
 * was never a backend gap. Selecting such a provider was a dead end: the request
 * went upstream with no credential and failed with an error the user could not
 * act on.
 *
 * Two properties matter and are asserted separately. The entry flow exists and
 * the key reaches the request. And the key is not persisted anywhere, because a
 * BYOK secret in localStorage is a credential at rest on a shared machine.
 */

const streamCalls: Array<{ prompt: string; providerKey?: string }> = [];
let providerCatalog: Array<{ name: string; configured: boolean; needsKey: boolean }> = [];

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    api: vi.fn(async (path: string) => {
      if (path.includes("/ai/providers")) {
        return { data: { active: "disabled", available: providerCatalog } };
      }
      return { data: null };
    }),
  };
});

vi.mock("../../lib/ai", () => ({
  aiStream: (
    req: { prompt: string; providerKey?: string },
    handlers: { onDelta: (d: string) => void; onEvidence: (ev: unknown) => void },
  ) =>
    (async () => {
      streamCalls.push(req);
      handlers.onDelta("answered");
      handlers.onEvidence({ provider: "x", model: "m", confidence: 0.8, evidence: [] });
      await new Promise((r) => setTimeout(r, 0));
      return handlers;
    })(),
}));

/**
 * A working stand-in for `useBoot`.
 *
 * The first version of this mock returned `{state: "ok"}` and ignored the
 * loader it was given, so `load()` never ran, `providers` stayed null, and the
 * provider toolbar never rendered. The copilot's own conversation log renders
 * regardless, so a test that only looked at turns would have passed anyway —
 * which is exactly the kind of mock that makes a suite agree with a broken page.
 */
function useBootStub(load: () => Promise<void>) {
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState<string | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    load()
      .then(() => {
        if (alive) setState("ok");
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
        setState("error");
      });
    return () => {
      alive = false;
    };
  }, [load]);
  return { state, error };
}

vi.mock("../../components/ui", async () => {
  const actual = await vi.importActual<typeof import("../../components/ui")>(
    "../../components/ui",
  );
  return { ...actual, useBoot: useBootStub };
});

beforeEach(() => {
  streamCalls.length = 0;
  localStorage.clear();
  sessionStorage.clear();
  providerCatalog = [
    { name: "disabled", configured: true, needsKey: false },
    { name: "openrouter", configured: false, needsKey: true },
    { name: "openai", configured: true, needsKey: true },
  ];
});

async function ready() {
  render(<Copilot />);
  // Wait for the provider list, not the conversation log: the toolbar renders
  // only once `providers` has loaded, and the log is present before that.
  await waitFor(() => expect(screen.getByLabelText("Ask using")).toBeInTheDocument());
}

async function chooseProvider(name: string) {
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText("Ask using"), name);
  return user;
}

async function ask(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByRole("textbox", { name: /question/i }), text);
  await user.click(screen.getByRole("button", { name: /^send$/i }));
}

describe("bring-your-own-key", () => {
  it("shows a key field only for a provider that needs one and has none", async () => {
    await ready();
    expect(screen.queryByLabelText(/API key/i)).not.toBeInTheDocument();

    // Needs a key and the server has none -> the field appears.
    await chooseProvider("openrouter");
    expect(screen.getByLabelText("openrouter API key")).toBeInTheDocument();

    // Needs a key but the server is already configured -> no field, because
    // typing one would override a working deployment key for no reason.
    await chooseProvider("openai");
    expect(screen.queryByLabelText(/API key/i)).not.toBeInTheDocument();
  });

  it("sends the key with the request", async () => {
    await ready();
    const user = await chooseProvider("openrouter");
    await user.type(screen.getByLabelText("openrouter API key"), "sk-test-123");
    await ask(user, "which supplier is single-sourced?");
    await waitFor(() => expect(streamCalls).toHaveLength(1));
    expect(streamCalls[0].providerKey).toBe("sk-test-123");
  });

  it("refuses to send without a key, and says why", async () => {
    // Upstream would answer 401 and the user would see an error they cannot act
    // on. Refusing locally names the actual problem.
    await ready();
    const user = await chooseProvider("openrouter");
    await ask(user, "hello");
    expect(streamCalls).toHaveLength(0);
    await waitFor(() =>
      expect(screen.getByText(/needs an API key/i)).toBeInTheDocument(),
    );
  });

  it("does not persist the key anywhere", async () => {
    await ready();
    const user = await chooseProvider("openrouter");
    await user.type(screen.getByLabelText("openrouter API key"), "sk-secret-value");

    // The strongest form of the check: nothing in either storage contains it.
    expect(JSON.stringify(localStorage)).not.toContain("sk-secret-value");
    expect(JSON.stringify(sessionStorage)).not.toContain("sk-secret-value");
  });

  it("clears the key on request", async () => {
    await ready();
    const user = await chooseProvider("openrouter");
    const input = screen.getByLabelText("openrouter API key") as HTMLInputElement;
    await user.type(input, "sk-abc");
    expect(input.value).toBe("sk-abc");
    await user.click(screen.getByRole("button", { name: /clear key/i }));
    expect(input.value).toBe("");
  });
});
