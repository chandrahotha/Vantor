import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthScreen, useBoot } from "./ui";
import * as auth from "../lib/auth";

/**
 * The auth gate is the product's front door.
 *
 * It used to hold one line: a session exists if and only if Keycloak returned a
 * signed token carrying a tenant. Sign-in is local and passwordless now, and
 * the line it has to hold has shifted — but not softened. The client still
 * cannot manufacture a session; only the API can issue one, and only a token
 * that names a tenant is accepted. What is new is the requirement that a
 * session *survive*: the previous build re-checked an unreachable identity
 * provider every 45 seconds and signed the user out when the check failed, so
 * switching to another window and back dropped them onto the sign-in screen.
 *
 * Each test below asserts on the absence of a session as carefully as on its
 * presence.
 */

vi.mock("../lib/api", () => ({
  setTokenGetter: vi.fn(),
  setRefreshFn: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
  api: vi.fn(),
}));

const LIVE = () => ({
  token: "header.payload.signature",
  name: "Administrator",
  tenant: "vantor-corp",
  roles: ["Buyer"],
  expiresAt: Date.now() + 60 * 60 * 1000,
});

function envelope(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => ({ data, pagination: null, error: null, requestId: "t" }),
  } as unknown as Response;
}

beforeEach(() => {
  localStorage.clear();
  auth.setSession(null);
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("no identity is ever manufactured on the client", () => {
  it("has no session at module load", () => {
    expect(auth.getSession()).toBeNull();
  });

  it("restores nothing when storage is empty", () => {
    expect(auth.restoreSession()).toBeNull();
    expect(auth.getSession()).toBeNull();
  });

  it("discards a stored session that has expired rather than replaying it", () => {
    // A token the API will reject is worse than no token: it renders a
    // signed-in shell in which every panel 401s.
    localStorage.setItem("vantor.session", JSON.stringify({ ...LIVE(), expiresAt: Date.now() - 1000 }));
    expect(auth.restoreSession()).toBeNull();
    expect(localStorage.getItem("vantor.session")).toBeNull();
  });

  it("discards a malformed stored session instead of repairing it", () => {
    localStorage.setItem("vantor.session", "{not json");
    expect(auth.restoreSession()).toBeNull();
  });

  it("refuses a server response that carries no tenant", async () => {
    // Every row is scoped by tenant, so a session without one can only 403.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      envelope({ token: "a.b.c", expiresIn: 3600, user: { name: "X", tenant: "", roles: [] } }),
    );
    await expect(auth.signIn()).rejects.toThrow(/no tenant/i);
    expect(auth.getSession()).toBeNull();
  });

  it("refuses a server response with no token", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(envelope({ expiresIn: 3600, user: {} }));
    await expect(auth.signIn()).rejects.toThrow(/did not return a session token/i);
    expect(auth.getSession()).toBeNull();
  });
});

describe("sign-in", () => {
  it("stores the session the API issued, and only that", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      envelope({
        token: "a.b.c",
        expiresIn: 3600,
        user: { name: "Administrator", tenant: "vantor-corp", roles: ["Buyer", "Approver"] },
      }),
    );
    const s = await auth.signIn();
    expect(s.token).toBe("a.b.c");
    expect(s.tenant).toBe("vantor-corp");
    expect(s.roles).toEqual(["Approver", "Buyer"]);
    expect(JSON.parse(localStorage.getItem("vantor.session")!).token).toBe("a.b.c");
  });

  it("names the address it could not reach when the API is down", async () => {
    // The old screen redirected to the identity provider, so an unreachable
    // host took the user out of the app entirely and left them on the
    // browser's "can't reach this page" with nothing actionable.
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(auth.signIn()).rejects.toThrow(/Could not reach the VANTOR API/);
  });

  it("clears the stored session on logout", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      envelope({ token: "a.b.c", expiresIn: 3600, user: { name: "A", tenant: "t", roles: [] } }),
    );
    await auth.signIn();
    auth.logout();
    expect(auth.getSession()).toBeNull();
    expect(localStorage.getItem("vantor.session")).toBeNull();
  });
});

describe("a session survives the things that used to end it", () => {
  it("does not sign the user out because a renewal failed", async () => {
    // This is the regression behind "I switch windows and come back and it has
    // logged me out". A renewal failure is not proof the session is dead; the
    // token in hand has its own expiry and is still good until it passes.
    vi.useFakeTimers();
    auth.setSession(LIVE());
    const onExpired = vi.fn();
    const stop = auth.keepFresh(onExpired);
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
    await vi.advanceTimersByTimeAsync(5 * 60_000);
    expect(onExpired).not.toHaveBeenCalled();
    expect(auth.getSession()).not.toBeNull();
    stop();
  });

  it("ends the session only once the token has actually expired", async () => {
    vi.useFakeTimers();
    auth.setSession({ ...LIVE(), expiresAt: Date.now() + 30_000 });
    const onExpired = vi.fn();
    const stop = auth.keepFresh(onExpired);
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
    await vi.advanceTimersByTimeAsync(3 * 60_000);
    expect(onExpired).toHaveBeenCalled();
    stop();
  });
});

describe("the boot gate", () => {
  function Probe() {
    const { state } = useBoot(async () => {});
    return <div data-testid="state">{state}</div>;
  }

  it("shows the sign-in screen when there is no stored session", async () => {
    render(<Probe />);
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("signin"));
  });

  it("adopts a stored session without asking the API for another", async () => {
    // A reload, a Fast Refresh, or returning to a backgrounded tab must not
    // cost a round trip — and must not bounce the user to the sign-in screen.
    localStorage.setItem("vantor.session", JSON.stringify(LIVE()));
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<Probe />);
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("ok"));
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("the sign-in screen", () => {
  it("asks for no credentials and offers exactly one way in", () => {
    render(<AuthScreen state="signin" />);
    expect(screen.queryByLabelText(/password/i)).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByRole("button", { name: /log in to vantor/i })).toBeInTheDocument();
  });

  it("reports a failed sign-in in place instead of navigating away", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    render(<AuthScreen state="signin" />);
    await userEvent.click(screen.getByRole("button", { name: /log in to vantor/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/Could not reach the VANTOR API/),
    );
  });
});
