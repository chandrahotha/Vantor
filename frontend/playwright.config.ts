import { defineConfig, devices } from '@playwright/test';

/**
 * The port the web app is served on.
 *
 * It was hardcoded to 3000 in both the Playwright config and the `dev` script,
 * with `reuseExistingServer: !process.env.CI` beside it. That combination has
 * a failure mode that looks like a product bug: if anything else is already
 * listening on 3000, Playwright silently reuses *it* and the suite runs
 * against whatever that is — a different application, a stale build, or an
 * unrelated dev server — and reports page-level timeouts instead of saying
 * "the port was taken".
 *
 * `PORT` is Next.js's own environment variable, so `next dev` and
 * `next start` honour it without a shell-specific default expression (which
 * would not work on Windows). `E2E_PORT` moves the whole suite — config,
 * server and base URL — together, so a local run never has to fight another
 * project for a port.
 */
const PORT = Number(process.env.E2E_PORT ?? 3000);
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    env: {
      PORT: String(PORT),
      NEXT_PUBLIC_API_URL: "http://localhost:8000",
      NEXT_PUBLIC_KEYCLOAK_URL: "http://localhost:8080",
    }
  },
});
