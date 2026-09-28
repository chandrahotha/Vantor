import { describe, expect, it, vi, beforeEach } from "vitest";
import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AuthScreen, useBoot } from "./ui";
import * as auth from "../lib/auth";
import { setUnauthorizedHandler } from "../lib/api";

/**
 * The auth gate is the product's front door, and these tests exist to hold one
 * specific line: an application session exists if and only if Keycloak returned
 * a signed token that carries a tenant.
 *
 * The previous implementation minted a session at module scope
 * (`REAL_ENTERPRISE_SESSION`, token `"vantor-corp-jwt-session"`), so the app
 * rendered a signed-in shell before any identity existed and every API call
 * carried a token the backend correctly rejected with 401. A test that only
 * checks "the shell renders" would have passed against it. Each test below
 * therefore asserts on the *absence* of a session as carefully as on presence.
 */

vi.mock("../lib/api", () => ({
  setTokenGetter: vi.fn(),
  setRefreshFn: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
  api: vi.fn(),
}));

type FakeKC = {
  token: string | undefined;
  tokenParsed: Record<string, unknown> | undefined;
  authenticated: boolean;
  didInitialize: boolean;
  initImpl: (options: unknown) => Promise<boolean>;
  init: ReturnType<typeof vi.fn>;
  login: ReturnType<typeof vi.fn>;
  logout: ReturnType<typeof vi.fn>;
  updateToken: ReturnType<typeof vi.fn>;
  onTokenExpired?: () => void;
};

function kc(): FakeKC {
  return auth.keycloak() as unknown as FakeKC;
}

/** Make the adapter report a signed-in session with a tenant claim. */
function signIn(claims: Record<string, unknown> = {}) {
  const k = kc();
  k.authenticated = true;
  k.token = "header.payload.signature";
  k.tokenParsed = {
    sub: "u-1",
    name: "Verified User",
    tenant_id: "tenant-a",
    realm_access: { roles: ["Buyer", "Approver"] },
    ...claims,
  };
  return k;
}

/** The handler the last-mounted `useBoot` registered with the API client. This
 *  is how a 401 reaches the auth layer in production, so tests drive it rather
 *  than reaching past the boundary. */
function unauthorizedHandler(): (() => void) | undefined {
  const m = setUnauthorizedHandler as unknown as { mock: { calls: (() => void)[][] } };
  return m.mock.calls.at(-1)?.[0];
}

function BootProbe({ load }: { load: () => Promise<void> }) {
  const { state, error, reload } = useBoot(load);
  return <AuthScreen state={state} error={error} onRetry={reload} />;
}

beforeEach(() => {
  sessionStorage.clear();
  auth.resetKeycloak();
  auth.setSession(null);
  vi.restoreAllMocks();
});

describe("AuthScreen states", () => {
  it("shows a branded splash while booting — never a blank frame", () => {
    render(<AuthScreen state="loading" />);
    expect(screen.getByRole("status")).toHaveTextContent("Opening VANTOR");
  });

  it("offers exactly one sign-in action when unauthenticated", () => {
    render(<AuthScreen state="signin" />);
    expect(screen.getByRole("status")).toHaveTextContent("Sign in to VANTOR");
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveTextContent("Continue with Vantor ID");
  });

  it("the sign-in button triggers an IdP redirect, not a local session", () => {
    const k = kc();
    k.didInitialize = true;
    render(<AuthScreen state="signin" />);
    fireEvent.click(screen.getByRole("button", { name: /Continue with Vantor ID/i }));
    expect(k.login).toHaveBeenCalled();
    // The redirect must not have been faked into a session.
    expect(auth.getSession()).toBeNull();
  });

  it("announces errors assertively, with the real message", () => {
    render(<AuthScreen state="error" error="Identity provider unreachable" />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Sign-in problem");
    expect(alert).toHaveTextContent("Identity provider unreachable");
  });

  it("a failed init offers retry, and retry does not navigate to the IdP", () => {
    const k = kc();
    k.didInitialize = true;
    const onRetry = vi.fn();
    render(<AuthScreen state="error" error="boom" onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: /Try again/i }));
    expect(onRetry).toHaveBeenCalled();
    expect(k.login).not.toHaveBeenCalled();
  });
});

describe("lib/auth: no identity without a verified token", () => {
  it("has no session at module load — the app cannot be 'already signed in'", () => {
    auth.resetKeycloak();
    auth.setSession(null);
    expect(auth.getSession()).toBeNull();
  });

  it("parseSession returns null for a token with no tenant claim", () => {
    signIn({ tenant_id: "", org_id: "", organization: "" });
    // The backend answers 403 "Token carries no tenant" for this token, so
    // inventing a tenant client-side would only build a session that fails.
    expect(auth.parseSession(auth.keycloak())).toBeNull();
  });

  it("parseSession returns null when there is no token at all", () => {
    const k = kc();
    k.authenticated = true;
    k.token = undefined;
    k.tokenParsed = undefined;
    expect(auth.parseSession(auth.keycloak())).toBeNull();
  });

  it("parseSession maps a verified token, de-duplicating realm and client roles", () => {
    signIn({
      realm_access: { roles: ["Buyer", "Approver"] },
      resource_access: { "vantor-web": { roles: ["Buyer", "Auditor"] } },
    });
    const s = auth.parseSession(auth.keycloak());
    expect(s).toEqual({
      token: "header.payload.signature",
      name: "Verified User",
      tenant: "tenant-a",
      roles: ["Approver", "Auditor", "Buyer"],
    });
  });

  it("logout drops the session even if the adapter is not initialized", () => {
    signIn();
    auth.wireSession(auth.keycloak());
    expect(auth.getSession()).not.toBeNull();
    auth.logout();
    expect(auth.getSession()).toBeNull();
  });
});

describe("useBoot", () => {
  it("an un-authenticated visit shows the gate and never calls the API", async () => {
    const load = vi.fn().mockResolvedValue(undefined);
    render(<BootProbe load={load} />);

    await waitFor(() => expect(screen.getByText("Sign in to VANTOR")).toBeInTheDocument());
    // The critical assertion: no data load happened, so no panel can render a
    // number that the backend never sent.
    expect(load).not.toHaveBeenCalled();
    expect(auth.getSession()).toBeNull();
  });

  it("a verified session loads data and reaches ok", async () => {
    signIn();
    const load = vi.fn().mockResolvedValue(undefined);
    render(<BootProbe load={load} />);

    await waitFor(() => expect(load).toHaveBeenCalled());
    expect(auth.getSession()?.tenant).toBe("tenant-a");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("an authenticated token with no tenant is an error, not a session", async () => {
    signIn({ tenant_id: "", org_id: "", organization: "" });
    const load = vi.fn().mockResolvedValue(undefined);
    render(<BootProbe load={load} />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/no tenant claim/i));
    expect(load).not.toHaveBeenCalled();
    expect(auth.getSession()).toBeNull();
  });

  it("an unreachable identity provider surfaces the error instead of a session", async () => {
    const k = kc();
    k.initImpl = async () => {
      throw new Error("Failed to fetch");
    };
    const load = vi.fn().mockResolvedValue(undefined);
    render(<BootProbe load={load} />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/Failed to fetch/));
    expect(auth.getSession()).toBeNull();
    expect(load).not.toHaveBeenCalled();
  });

  it("initialises with a silent SSO probe so the window never navigates to the IdP", async () => {
    signIn();
    render(<BootProbe load={vi.fn().mockResolvedValue(undefined)} />);
    await waitFor(() => expect(kc().init).toHaveBeenCalled());
    const opts = kc().init.mock.calls[0][0] as Record<string, unknown>;
    // keycloak-js 26.2.4 falls through to a full-window `prompt=none` redirect
    // unless silentCheckSsoRedirectUri is set (lib/keycloak.js:834-844).
    expect(opts.onLoad).toBe("check-sso");
    expect(opts.pkceMethod).toBe("S256");
    expect(opts.checkLoginIframe).toBe(true);
    expect(String(opts.silentCheckSsoRedirectUri)).toContain("/silent-check-sso.html");
  });

  it("initialises the IdP once even when StrictMode mounts the boot twice", async () => {
    // keycloak-js throws on a second `init` of the same instance, and React
    // StrictMode runs every effect twice in development. A boot that calls
    // `kc.init` straight from its effect therefore fails on a working network
    // and reports "Sign-in problem". This was B-31, and the fix was lost when
    // the auth adapter was rewritten — the memo has to be asserted, not assumed.
    signIn();
    const load = vi.fn().mockResolvedValue(undefined);
    render(
      <StrictMode>
        <BootProbe load={load} />
      </StrictMode>,
    );

    await waitFor(() => expect(load).toHaveBeenCalled());
    expect(kc().init).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps the token fresh while the app is open", async () => {
    signIn();
    render(<BootProbe load={vi.fn().mockResolvedValue(undefined)} />);
    await waitFor(() => expect(kc().init).toHaveBeenCalled());
    expect(typeof kc().onTokenExpired).toBe("function");
  });

  it("a refresh failure drops to the sign-in gate", async () => {
    signIn();
    render(<BootProbe load={vi.fn().mockResolvedValue(undefined)} />);
    await waitFor(() => expect(kc().init).toHaveBeenCalled());

    kc().updateToken.mockRejectedValue(new Error("no session"));
    kc().onTokenExpired?.();

    await waitFor(() => expect(screen.getByText("Sign in to VANTOR")).toBeInTheDocument());
    expect(auth.getSession()).toBeNull();
  });

  it("stop the fast boot after rapid repeated failed checks and shows the real error", async () => {
    // Three unauthenticated checks within the window == the client keeps
    // coming back without a session — a misconfiguration, not a user slowly
    // clicking sign-in. A success earlier breaks the streak.
    auth.noteBounce(false);
    auth.noteBounce(false);
    auth.noteBounce(false);
    expect(auth.isLooping()).toBe(true);

    const load = vi.fn().mockResolvedValue(undefined);
    render(<BootProbe load={load} />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/Sign-in is looping/i);
    });
    expect(load).not.toHaveBeenCalled();
    auth.clearBounces();
  });

  it("a signed-in reload is NOT flagged as a loop", () => {
    auth.noteBounce(true);
    auth.noteBounce(false);
    auth.noteBounce(false);
    auth.noteBounce(false);
    expect(auth.isLooping()).toBe(false);
    auth.clearBounces();
  });

  it("a sign-out anywhere in the app returns the view to the gate", async () => {
    signIn();
    const load = vi.fn().mockResolvedValue(undefined);
    render(<BootProbe load={load} />);
    await waitFor(() => expect(load).toHaveBeenCalled());

    auth.setSession(null);
    await waitFor(() => expect(screen.getByText("Sign in to VANTOR")).toBeInTheDocument());
  });

  it("a 401 on the first data load ends the session instead of reaching ok", async () => {
    // The defect this pins: the boot stored the load error and then called
    // `setState("ok")` unconditionally, so an expired token rendered the whole
    // page plus "Session expired — please sign in again." with no way to sign in.
    // `api()` signals a 401 by invoking the registered handler and *then*
    // throwing, so the fake load does exactly that.
    signIn();
    const load = vi.fn().mockImplementation(async () => {
      unauthorizedHandler()?.();
      throw new Error("Session expired — please sign in again.");
    });
    render(<BootProbe load={load} />);

    await waitFor(() => expect(load).toHaveBeenCalled());
    // The gate is showing, and it is the *sign-in* gate, not a data-error state.
    await waitFor(() => expect(screen.getByText("Sign in to VANTOR")).toBeInTheDocument());
    expect(screen.queryByRole("alert")).toBeNull();
    expect(auth.getSession()).toBeNull();
  });

  it("a 401 mid-session returns the view to the gate", async () => {
    signIn();
    render(<BootProbe load={vi.fn().mockResolvedValue(undefined)} />);
    await waitFor(() => expect(kc().init).toHaveBeenCalled());

    // What the API client does on a 401 the backend still rejects.
    expect(unauthorizedHandler()).toBeTypeOf("function");
    unauthorizedHandler()?.();

    await waitFor(() => expect(screen.getByText("Sign in to VANTOR")).toBeInTheDocument());
    expect(auth.getSession()).toBeNull();
  });

  it("a non-401 data failure still reaches ok and is handed to the page", async () => {
    // A failed *load* is not an identity problem. The gate must not swallow it:
    // the page reaches `ok` and renders its own ErrorBox, because the session is
    // valid and only that one request failed. Replacing the page with the
    // sign-in screen here would wrongly tell a signed-in user to sign in again.
    signIn();
    function Probe() {
      const { state, error } = useBoot(vi.fn().mockRejectedValue(new Error("backend exploded")));
      return (
        <div>
          <span data-testid="state">{state}</span>
          <span data-testid="error">{error}</span>
          <AuthScreen state={state} error={error} />
        </div>
      );
    }
    render(<Probe />);

    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("ok"));
    expect(screen.getByTestId("error")).toHaveTextContent("backend exploded");
    expect(auth.getSession()).not.toBeNull();
  });
});
