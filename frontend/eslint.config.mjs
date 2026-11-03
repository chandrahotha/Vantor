import next from "eslint-config-next";
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

const config = [
  ...next,
  ...nextCoreWebVitals,
  ...nextTypeScript,
  {
    ignores: [".next/**", "out/**", "build/**", "node_modules/**", "next-env.d.ts"],
  },
];

// ---------------------------------------------------------------------------
// minimatch v11 guard
//
// `package.json` overrides `minimatch` to `^11.0.1` for the whole tree. That
// is the first release without CVE-2026-118764 (GHSA-g3hv-75wg-m249), the
// glob-parts amplification DoS in `firstPhasePreProcess()`.
//
// The override has one consequence worth knowing about: minimatch v3's module
// export was a *callable* function, and v11's is an object with a named
// `minimatch` export instead. Three ESLint plugins call the module directly —
// `eslint-plugin-import` does `require("minimatch")(...pattern)` and
// `eslint-plugin-react` / `eslint-plugin-jsx-a11y` do the same — so the
// handful of rules below throw `TypeError: minimatch is not a function` under
// v11.
//
// None of those rules is enabled here, and `eslint-config-next` does not
// enable them either (they are opt-in rules inside those plugins). They also
// only reach minimatch when a glob pattern is configured for them, so an
// unconfigured rule never calls it at all.
//
// This check exists so that "somebody enabled one of these later" is an
// error that says what to do, instead of a stack trace in the middle of a lint
// run with no explanation.
// ---------------------------------------------------------------------------
const MINIMATCH_CALLABLE_RULES = [
  "import/extensions",
  "import/no-extraneous-dependencies",
  "react/no-unstable-nested-components",
  "react/forbid-component-props",
  "react/jsx-pascal-case",
];

// Flat config: the last entry that mentions a rule wins, so the effective
// severity is the last one seen rather than the first.
const effectiveSeverity = new Map();
for (const entry of config) {
  for (const [rule, value] of Object.entries(entry.rules ?? {})) {
    effectiveSeverity.set(rule, value);
  }
}

const isOff = (value) =>
  value === 0 ||
  value === "off" ||
  (Array.isArray(value) && (value[0] === 0 || value[0] === "off"));

const incompatible = MINIMATCH_CALLABLE_RULES.filter((rule) => {
  const value = effectiveSeverity.get(rule);
  return value !== undefined && !isOff(value);
});

if (incompatible.length > 0) {
  throw new Error(
    `These rules call minimatch as a function, which minimatch v11 no longer ` +
      `supports, so they cannot run while the minimatch override is in place: ` +
      `${incompatible.join(", ")}.\n\n` +
      `Fix: leave them off, or drop the "minimatch" override from package.json ` +
      `and accept GHSA-g3hv-75wg-m249 until the upstream plugins migrate.`,
  );
}

export default config;
