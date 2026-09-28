import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

/** Shared test setup. */

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// jsdom does not implement scrollIntoView; components call it on deep links.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}

// next/navigation is not available outside the Next runtime.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

// The app is entirely OIDC-gated; unit tests must never open a real redirect.
// This fake mirrors the keycloak-js 26.2.4 surface the app actually calls, so a
// test that drives it is exercising the same code path the browser will take.
vi.mock("keycloak-js", () => {
  class FakeKeycloak {
    token: string | undefined;
    refreshToken: string | undefined;
    tokenParsed: Record<string, unknown> | undefined;
    authenticated = false;
    /** keycloak-js sets this inside `init`; `initKeycloak` short-circuits on it. */
    didInitialize = false;
    onTokenExpired?: () => void;
    /** Overridden by tests that need init to fail or to hang. */
    initImpl: (options: unknown) => Promise<boolean> = async () => true;

    constructor(config: unknown) {
      // Real config is irrelevant here; asserting on it would only pin env vars.
      void config;
    }

    init = vi.fn(async (options: unknown) => {
      const result = await this.initImpl(options);
      this.didInitialize = true;
      return result;
    });

    login = vi.fn();
    logout = vi.fn();
    updateToken = vi.fn().mockResolvedValue(true);
    clearToken = vi.fn();
  }
  return { default: FakeKeycloak };
});
