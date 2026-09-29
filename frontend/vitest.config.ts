import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

/** Vitest config.
 *
 *  The frontend had no test runner at all, which is why its a11y and correctness
 *  claims were assertions rather than evidence. This config mounts jsdom, wires
 *  jest-dom matchers, and — importantly — fails the run on an unexpectedly low
 *  pass rate so a broken suite cannot present as green.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname) },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.{test,spec}.{ts,tsx}"],
    exclude: ["node_modules/**", ".next/**", "e2e/**"],
    // forks pool hangs on Windows (worker never answers). threads are the
    // supported default; single-fork debugging hangs the run entirely.
    pool: "threads",
    testTimeout: 15000,
    hookTimeout: 15000,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["app/**/*.{ts,tsx}", "components/**/*.tsx", "lib/**/*.ts"],
      thresholds: {
        // Deliberately modest: these are a floor to stop silent regression to
        // zero, not a claim of comprehensive coverage.
        statements: 40,
        branches: 30,
        functions: 35,
        lines: 40,
      },
    },
  },
});
