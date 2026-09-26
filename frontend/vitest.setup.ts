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
vi.mock("keycloak-js", () => {
  class FakeKeycloak {
    token: string | undefined;
    tokenParsed: Record<string, unknown> | undefined;
    authenticated = false;
    onTokenExpired?: () => void;
    init = vi.fn().mockResolvedValue(true);
    updateToken = vi.fn().mockResolvedValue(true);
  }
  return { default: FakeKeycloak };
});
