import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * VNT-045: the approval queue had no route and no navigation entry. It rendered
 * only inside the copilot page, so the surface a manager uses most — the one
 * that governs spending money — was filed under an AI feature.
 *
 * Nothing enforced the relationship between the pages that exist and the links
 * that reach them, so a surface can be missing, or a link can be dead, and
 * nothing notices until a person clicks. These are structural checks over the
 * filesystem, so they cost nothing and run on every push.
 *
 * The deliberate exception list is short and each entry says why. Anything added
 * to it has to justify itself, which is the point.
 */

/** Routes that are intentionally not in the primary navigation. */
const NOT_IN_NAV = new Map<string, string>([
  // A detail page reached by clicking a row, not a destination of its own.
  ["/suppliers/[id]", "supplier 360 is opened from a row on /suppliers"],
]);

const ROOT = path.resolve(__dirname, "..");

function pageRoutes(dir = path.join(ROOT, "app")): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      found.push(...pageRoutes(full));
    } else if (entry === "page.tsx" || entry === "page.ts") {
      const rel = path.relative(path.join(ROOT, "app"), path.dirname(full));
      found.push(rel === "" ? "/" : `/${rel.split(path.sep).join("/")}`);
    }
  }
  return found.sort();
}

/**
 * Every href the shell actually renders.
 *
 * Not just the `NAV` array: the shell has a second, hardcoded "Account" section
 * that links to alerts. Reading only `NAV` reported `/notifications` as an
 * orphan when the link was right there, which is the same class of error as the
 * one this file exists to catch - a check that looks in the wrong place is worse
 * than no check, because it produces a confident false alarm.
 */
function navHrefs(): string[] {
  const source = readFileSync(path.join(ROOT, "components", "Shell.tsx"), "utf8");
  const fromTuple = [...source.matchAll(/\[\s*"[^"]*",\s*"[^"]*",\s*"(\/[^"]*)"\s*\]/g)]
    .map((m) => m[1]);
  const fromLink = [...source.matchAll(/href="(\/[^"]*)"/g)].map((m) => m[1]);
  return [...new Set([...fromTuple, ...fromLink])].sort();
}

describe("navigation covers the product", () => {
  const routes = pageRoutes();
  const hrefs = navHrefs();

  it("finds the pages on disk", () => {
    // If this ever finds nothing, the checks below pass vacuously - which is
    // exactly how a structural test becomes a test that agrees with anything.
    expect(routes.length).toBeGreaterThan(10);
    expect(routes).toContain("/");
    expect(routes).toContain("/suppliers");
  });

  it("reaches every page from the navigation", () => {
    const reachable = new Set(hrefs);
    const orphans = routes.filter(
      (route) => !reachable.has(route) && !NOT_IN_NAV.has(route),
    );
    expect(
      orphans,
      `these pages exist but nothing in the navigation links to them: ${orphans.join(", ")}. ` +
        "Either the surface is missing from the product, or it needs an entry in NAV — " +
        "and if it genuinely should not be linked, say why in NOT_IN_NAV.",
    ).toEqual([]);
  });

  it("has no navigation entry pointing at a page that does not exist", () => {
    const existing = new Set(routes);
    const dead = hrefs.filter((href) => !existing.has(href));
    expect(dead, `NAV links to routes with no page: ${dead.join(", ")}`).toEqual([]);
  });

  it("has a route for the approval queue", () => {
    // Named explicitly because it is the surface whose absence caused the
    // finding, and a general orphan check can be satisfied by unrelated pages.
    expect(routes).toContain("/approvals");
    expect(hrefs).toContain("/approvals");
  });

  it("lists every route in the sitemap route table", () => {
    const source = readFileSync(path.join(ROOT, "app", "sitemap.ts"), "utf8");
    const listed = [...source.matchAll(/path:\s*"([^"]*)"/g)].map((m) => m[1]);
    const missing = routes.filter(
      (route) => !NOT_IN_NAV.has(route) && !listed.includes(route === "/" ? "" : route),
    );
    expect(
      missing,
      `pages absent from the sitemap route table: ${missing.join(", ")}`,
    ).toEqual([]);
  });
});
