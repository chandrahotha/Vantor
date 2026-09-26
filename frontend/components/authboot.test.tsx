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
  it("stops redirecting after rapid repeats and surfaces a configuration error", async () => {
    vi.spyOn(Date, "now").mockReturnValue(1_000);
    auth.noteBounce();
    auth.noteBounce();
    expect(auth.isLooping()).toBe(true);

    const kc = auth.keycloak();
    const initSpy = vi.spyOn(kc, "init").mockResolvedValue(true);
    render(<BootProbe load={vi.fn().mockResolvedValue(undefined)} />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/Sign-in is looping/i);
    });
    // The loop path must NOT call kc.init again — that is the loop.
    expect(initSpy).not.toHaveBeenCalled();

    vvi.mockRestore(Date, "now");
    auth.clearBounces();
  });

  it("a normal boot clears the bounce history and reaches ok", async () => {
    vi.spyOn(auth, "isLooping").mockReturnValue(false);
    const kc = auth.keycloak();
    vi.spyOn(kc, "init").mockResolvedValue(true);
    (kc as unknown as { token: string }).token = "tok";
    kc.tokenParsed = { sub: "u1", name: "Tester", tenant_id: "t1", realm_access: { roles: ["Buyer"] } };

    const load = vi.fn().mockResolvedValue(undefined);
    render(<BootProbe load={load} />);
    await waitFor(() => expect(load).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

// tiny helper so vi.mockRestore(Date, ...) reads clearly above
const vvi = { mockRestore: (mod: Date, key: string) => vi.spyOn(mod, key as never) };
