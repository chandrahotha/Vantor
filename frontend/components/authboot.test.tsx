import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AuthScreen, useBoot } from "./ui";
import * as auth from "../lib/auth";

/**
 * The auth gate is the product's front door. Two failure modes matter more
 * than any other: a blank frame that vanishes into an IdP redirect (which read
 * as "the app is broken" to the user), and a redirect loop when the realm is
 * misconfigured. Both are covered here at the component level because loops
 * cannot be trusted to "just work" — they emerge from wiring.
 */

vi.mock("../lib/api", () => ({
  setTokenGetter: vi.fn(),
  setRefreshFn: vi.fn(),
  api: vi.fn(),
}));

function BootProbe({ load }: { load: () => Promise<void> }) {
  const { state, error } = useBoot(load);
  return <AuthScreen state={state} error={error} />;
}

beforeEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("AuthScreen states", () => {
  it("shows a branded splash while booting — never a blank frame", () => {
    render(<AuthScreen state="loading" />);
    expect(screen.getByRole("status")).toHaveTextContent("Opening VANTOR");
  });

  it("offers a sign-in action when unauthenticated rather than hanging silently", () => {
    render(<AuthScreen state="signin" />);
    expect(screen.getByRole("status")).toHaveTextContent("Sign in to VANTOR");
    expect(screen.getByRole("button", { name: /Continue with Vantor ID/i })).toBeInTheDocument();
  });

  it("announces errors assertively, with the real message", () => {
    render(<AuthScreen state="error" error="Identity provider unreachable" />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Could not start VANTOR");
    expect(alert).toHaveTextContent("Identity provider unreachable");
  });
});

describe("useBoot loop breaker", () => {
  it("stops redirecting after rapid repeated failed checks and shows the real error", async () => {
    // Three unauthenticated checks within the window == the client keeps
    // coming back without a session — a misconfiguration, not the user slowly
    // clicking sign-in. A successful sign-in within the same window breaks it.
    auth.noteBounce(false);
    auth.noteBounce(false);
    auth.noteBounce(false);
    expect(auth.isLooping()).toBe(true);

    const kc = auth.keycloak() as unknown as { init: ReturnType<typeof vi.fn>; authenticated: boolean; didInitialize: boolean };
    const initSpy = vi.spyOn(kc, "init").mockResolvedValue(true);
    render(<BootProbe load={vi.fn().mockResolvedValue(undefined)} />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/Sign-in is looping/i);
    });
    vi.restoreAllMocks();
    auth.clearBounces();
  });

  it("a signed-in reload is NOT flagged as a loop", async () => {
    auth.noteBounce(true);
    auth.noteBounce(false);
    auth.noteBounce(false);
    auth.noteBounce(false);
    // A success earlier breaks the streak — reloads while signed in are not loops.
    expect(auth.isLooping()).toBe(false);
    auth.clearBounces();
  });

  it("a normal boot checks SSO, hydrates the session and reaches ok", async () => {
    vi.spyOn(auth, "isLooping").mockReturnValue(false);
    const kc = auth.keycloak() as unknown as {
      init: ReturnType<typeof vi.fn>; authenticated: boolean;
      token: string; tokenParsed: Record<string, unknown>;
    };
    vi.spyOn(kc, "init").mockResolvedValue(true);
    kc.authenticated = true;
    kc.token = "tok";
    kc.tokenParsed = { sub: "u1", name: "Tester", tenant_id: "t1", realm_access: { roles: ["Buyer"] } };

    const load = vi.fn().mockResolvedValue(undefined);
    render(<BootProbe load={load} />);
    await waitFor(() => expect(load).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("login() never throws when the adapter is not initialized yet", async () => {
    expect(() => auth.login()).not.toThrow();
  });
});

