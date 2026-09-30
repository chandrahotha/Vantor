/** Frontend ↔ API contract.
 *
 *  Nothing in this repository checked that the web app calls endpoints the API
 *  actually serves. The backend has 355 pytest cases and the frontend had 151
 *  unit tests, and between the two sat the one question neither answered: does
 *  the UI ask the server for things the server has?
 *
 *  A mismatch here is invisible in every other gate. It typechecks, it lints,
 *  it builds, and the unit tests pass because they mock `api()`. It surfaces as
 *  a 404 in front of a user, on whichever screen nobody clicked before release
 *  — and `api()` turns a 404 into the generic "Request failed (404)", so the
 *  report that comes back is "the page is broken", not "that route was renamed
 *  in the backend three commits ago".
 *
 *  `api/openapi.json` is generated from the FastAPI app and CI already fails on
 *  drift between it and the server, so it is a trustworthy statement of what
 *  exists. This test is the other half of that: the spec is checked against the
 *  server, and the client is checked against the spec.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(import.meta.dirname, "..");
const SPEC = path.resolve(ROOT, "..", "api", "openapi.json");

type Spec = { paths: Record<string, Record<string, unknown>> };

/** Every source file the app ships, excluding its own tests. */
function sources(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next" || entry === "e2e") continue;
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) sources(full, acc);
    else if (/\.(ts|tsx)$/.test(entry) && !/\.(test|spec)\./.test(entry)) acc.push(full);
  }
  return acc;
}

export type Call = { method: string; path: string; file: string; line: number };

/** Pull every `api("…", { method: … })` call out of a source file.
 *
 *  Brace-counted rather than regex-matched on the whole call: the options
 *  object routinely spans several lines and contains nested objects and
 *  template literals, and a naive `\{([^}]*)\}` stops at the first inner brace —
 *  which silently reports a POST as a GET. That is exactly the class of error
 *  this file exists to catch, so it must not make it itself.
 */
export function extractCalls(src: string, file: string): Call[] {
  const out: Call[] = [];
  // `api(` or `api<Type>(`, not `.api(` and not an identifier ending in "api".
  const re = /(^|[^.\w])api\s*(?:<[\s\S]*?>)?\s*\(/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src))) {
    const open = m.index + m[0].length - 1;
    // Walk to the matching close paren, tracking nesting and string context.
    let depth = 0;
    let i = open;
    let quote: string | null = null;
    for (; i < src.length; i++) {
      const c = src[i];
      const prev = src[i - 1];
      if (quote) {
        if (c === quote && prev !== "\\") quote = null;
        continue;
      }
      if (c === '"' || c === "'" || c === "`") { quote = c; continue; }
      if (c === "(" || c === "{" || c === "[") depth++;
      else if (c === ")" || c === "}" || c === "]") {
        depth--;
        if (depth === 0) break;
      }
    }
    const args = src.slice(open + 1, i);
    const pathMatch = /^\s*[`"']([^`"']*)/.exec(args);
    if (!pathMatch) continue;
    const raw = pathMatch[1];
    if (!raw.startsWith("/api/")) continue;
    const methodMatch = /\bmethod\s*:\s*["'](\w+)["']/.exec(args);
    out.push({
      method: (methodMatch?.[1] ?? "GET").toUpperCase(),
      path: raw,
      file: path.relative(ROOT, file).replace(/\\/g, "/"),
      line: src.slice(0, m.index).split("\n").length,
    });
  }
  return out;
}

/** `/api/v1/suppliers/${id}/contacts?x=1` -> `/api/v1/suppliers/{}/contacts` */
export function normalise(p: string): string {
  return p
    .split("?")[0]
    .replace(/\$\{[^}]*\}/g, "{}")
    .replace(/\/+$/, "");
}

const spec = JSON.parse(readFileSync(SPEC, "utf8")) as Spec;

/** The spec's own paths, reduced to the same shape. */
const served = new Map<string, Set<string>>();
for (const [p, ops] of Object.entries(spec.paths)) {
  const key = normalise(p.replace(/\{[^}]*\}/g, "{}"));
  const methods = served.get(key) ?? new Set<string>();
  for (const verb of Object.keys(ops)) {
    if (["get", "post", "put", "patch", "delete"].includes(verb)) methods.add(verb.toUpperCase());
  }
  served.set(key, methods);
}

/** Call sites whose *final* segment is built from a variable.
 *
 *  `app/shared/orders.tsx` drives the purchase-order lifecycle from a table
 *  (`PO_ACTIONS`), so it calls `/purchase-orders/${id}/${path}` where `path` is
 *  the chosen transition. Static analysis cannot resolve that, and silently
 *  skipping it would leave the lifecycle — the part of the product that moves
 *  money — as the one thing this test does not cover.
 *
 *  Each entry is expanded to its concrete values and every expansion is
 *  checked. Adding a transition to `PO_ACTIONS` without adding it here leaves
 *  it unverified, so the list is asserted to match the source below.
 */
const DYNAMIC_TAILS: Record<string, string[]> = {
  "/api/v1/purchase-orders/{}/{}": ["approve", "send"],
};

const rawCalls = sources(ROOT).flatMap((f) => extractCalls(readFileSync(f, "utf8"), f));

const calls: Call[] = rawCalls.flatMap((c) => {
  const expansions = DYNAMIC_TAILS[normalise(c.path)];
  if (!expansions) return [c];
  return expansions.map((tail) => ({ ...c, path: normalise(c.path).replace(/\{\}$/, tail) }));
});

describe("frontend ↔ API contract", () => {
  it("finds the call sites at all (guards the extractor itself)", () => {
    // A silently-empty extractor would make every assertion below vacuously
    // true, which is the failure mode of a test like this.
    expect(calls.length).toBeGreaterThan(50);
    expect(new Set(calls.map((c) => c.method))).toContain("POST");
    expect(new Set(calls.map((c) => c.method))).toContain("PATCH");
  });

  it("parses the method off a multi-line options object", () => {
    const sample = `
      await api("/api/v1/rfqs/x/quotes", {
        method: "POST",
        idemKey: newIdemKey(),
        body: JSON.stringify({ lines: [{ qty: 1 }] }),
      });
    `;
    expect(extractCalls(sample, "x.ts")).toEqual([
      expect.objectContaining({ method: "POST", path: "/api/v1/rfqs/x/quotes" }),
    ]);
  });

  it("keeps the purchase-order transition list in step with the source", () => {
    // If a transition is added to PO_ACTIONS and not to DYNAMIC_TAILS above, the
    // new endpoint ships unverified. This is what stops that.
    const orders = readFileSync(path.join(ROOT, "app", "shared", "orders.tsx"), "utf8");
    const start = orders.indexOf("const PO_ACTIONS");
    const block = orders.slice(start, orders.indexOf("\n};", start));
    expect(start).toBeGreaterThan(-1);
    const paths = [...block.matchAll(/\bpath:\s*"([^"]+)"/g)].map((m) => m[1]).sort();
    expect(paths).toEqual([...DYNAMIC_TAILS["/api/v1/purchase-orders/{}/{}"]].sort());
  });

  it("calls only paths the API serves", () => {
    const missing = calls
      .filter((c) => !served.has(normalise(c.path)))
      .map((c) => `${c.method} ${normalise(c.path)}  (${c.file}:${c.line})`);
    expect(Array.from(new Set(missing))).toEqual([]);
  });

  it("uses a method the API accepts on that path", () => {
    const wrong = calls
      .filter((c) => served.has(normalise(c.path)))
      .filter((c) => !served.get(normalise(c.path))!.has(c.method))
      .map((c) => {
        const allowed = [...served.get(normalise(c.path))!].sort().join("/");
        return `${c.method} ${normalise(c.path)} — API allows ${allowed}  (${c.file}:${c.line})`;
      });
    expect(Array.from(new Set(wrong))).toEqual([]);
  });
});
