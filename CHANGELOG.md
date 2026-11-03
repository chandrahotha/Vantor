<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# Changelog - VANTOR

All notable changes tracked here. Statuses: `PLANNED / IN DEVELOPMENT / IMPLEMENTED / TESTED / PRODUCTION READY`.

## [Unreleased]

### Security

- **All 18 open Dependabot security alerts closed in one consolidated refresh.**
  | Package | Alerts | From | To |
  |---|---|---|---|
  | `next` | 67–72 (runtime; 4 critical, 2 high) | 16.4.0 | 16.4.4 |
  | `undici` | 66, 73, 75, 76 (dev; 3 high, 1 medium) | 8.12.1 | 8.12.3 |
  | `vite` | 57–62 (dev; 1 high, 4 medium, 1 low) | 8.3.1 | 8.3.5 |
  | `@vitest/mocker` | 63, 64 (dev; 2 medium) | 5.0.2 | 5.1.0 |

  `eslint-config-next` moved in lockstep with `next` (they release together).
  `vite` was an unpinned peer transitive that npm had left at the vulnerable
  8.3.1; it is now an explicit devDependency so the advisory has a version to
  move. `@vitest/mocker` could not be updated at all before this change —
  `vitest` pinned it to an exact version, so Dependabot reported
  "update not possible" and silently did nothing; `vitest` 5.1.0 unblocks it.
  The `@vitest/mocker` and `vite` advisories were also unreachable behind
  Dependabot's `open-pull-requests-limit`, which was exhausted by the backlog.
- **`minimatch` overridden to `^11.0.1`** (GHSA-g3hv-75wg-m249, moderate,
  CVE-2026-118764 — denial of service via glob-parts amplification in
  `firstPhasePreProcess()`). The advisory was published on 2026-10-30, after
  the last dependency scan, so it only surfaced once this refresh re-scanned
  the tree. The flaw is in minimatch v10's pattern optimizer — v3 does not
  contain that code path — but the advisory's affected range is a blanket
  `< 11.0.1`, so every copy in the tree is flagged, including the v3 ones
  under `eslint-plugin-import`, `eslint-plugin-react` and
  `eslint-plugin-jsx-a11y`. Forcing the whole tree to v11 closes the alert and
  takes `npm audit` to **0 vulnerabilities across dev and prod** (it was 15
  moderate + 2 high).
  One consequence is guarded rather than left to chance: minimatch v3's
  module export was a callable function and v11's is an object, so five
  opt-in rules in those plugins (`import/extensions`,
  `import/no-extraneous-dependencies`, `react/no-unstable-nested-components`,
  `react/forbid-component-props`, `react/jsx-pascal-case`) cannot run under
  v11. None is enabled here and `eslint-config-next` does not enable them;
  `eslint.config.mjs` now checks the composed config and fails with an
  actionable message if one is ever switched on.
- **Backend pins refreshed to current releases.** `fastapi` 0.162.0,
  `starlette` 1.10.0, `uvicorn[standard]` 0.54.0, `pydantic` 2.14.2,
  `pydantic-settings` 2.16.2, `SQLAlchemy` 2.1.6, `alembic` 1.20.1,
  `psycopg[binary]` 3.3.6, `pgvector` 0.5.1, `PyJWT` 2.15.1,
  `cryptography` 50.0.2, `httpx` 0.28.1, `python-multipart` 0.0.33,
  `redis` 8.1.0, `pytest` 9.2.0, `pytest-asyncio` 1.4.1. `starlette` is now
  named explicitly: it is a transitive of `fastapi`, and seven advisories
  (DoS, request smuggling) live there — `pip-audit` only sees what is
  resolvable, so the security-relevant transitive must be pinned, not left to
  the resolver.

### Fixed

- **The Dockerfiles copied the developer's `node_modules` over the
  container's own install.** `frontend/Dockerfile` installs the dependencies
  and *then* copies the source:
  ```
  RUN npm ci        # the lockfile's exact tree, for this platform
  COPY . .          # ...overwritten by whatever the host happened to have
  ```
  There was no `.dockerignore`, so Docker's default applied: everything in
  the context was sent. A later `COPY` merges over an earlier layer, so the
  host's `node_modules` replaced the packages `npm ci` had just installed
  where their paths collided, and was added alongside them where they did not.
  The image therefore shipped the *developer's* dependency tree rather than
  the lockfile's — and, on a glibc host, glibc-compiled native modules in an
  Alpine (musl) image. The host's stale `.next` was copied over the build
  output as well.
  The root `Dockerfile` had the same defect in `COPY frontend/ ./`.
  Measured on a working checkout: **1.02 GB** of build context, 340 host
  packages copied into the image. With a `.dockerignore` per context: the
  context drops to the tracked source, and neither `node_modules` nor `.next`
  is copied.
- **No CI job built a Dockerfile — ever.** The `release` workflow publishes a
  GitHub release and never touches Docker, so the repository's primary
  delivery artefact was built by nobody, ever. A broken Dockerfile could
  reach `main` with no test noticing, which is exactly how the defect above
  survived. There is now an `images` job: the three Python images are built
  on every push (one `pip install` each, and they catch the failures that
  actually happen — a base image that no longer resolves, a requirements file
  that cannot be installed, a Dockerfile that no longer parses), and the two
  Node images are built on the weekly schedule and on a manual
  `full_suite: true` dispatch, because each runs a full `npm ci` and a
  production `next build`.
- **The Dockerfile base images were mutable tags.** `python:3.14-slim` and
  `node:22-alpine` are now pinned to digests, and `scripts/pin_digests.py
  --check` parses every `FROM` line and fails on an unpinned or malformed
  digest. The base image is where the build's supply chain enters — it
  carries the system packages, the interpreter, and the `npm ci` / `pip
  install` that run on top of it. The check tells a base image apart from a
  build stage by tracking the stage names the file itself defines, so
  `FROM web AS run` is not mistaken for an image to pull.
- **A file-backed SQLite database shared one connection across every request
  thread.** `get_engine()` gave `StaticPool` to every SQLite URL — a comment
  said "unit-test / local only", but the condition was `url.startswith("sqlite")`,
  which also matched `sqlite:////data/vantor.db`, the single-container
  image's database. `StaticPool` hands out *one* connection to all threads,
  which is the only way to make an in-memory SQLite database work, but a
  SQLite connection is not safe for concurrent use. Concurrent requests
  interleaved on it and surfaced as `sqlite3.InterfaceError: bad parameter or
  other API misuse` and `IndexError: tuple index out of range` inside
  SQLAlchemy's row loading — the second one because a thread found the result
  row it expected had been consumed by another thread.
  In-memory SQLite still gets `StaticPool` (its contents live inside the
  connection, so a second connection would be a second, empty database); a
  file-backed database now gets the dialect's own `QueuePool`, one connection
  per thread. `backend/tests/test_sqlite_pooling.py` reproduces the original
  failure and guards the fix.
- **Error responses carried no CORS grant.** Starlette installs a catch-all
  `Exception` handler on `ServerErrorMiddleware`, the outermost layer —
  *outside* every `add_middleware` call. A response produced there therefore
  never passed back through the CORS middleware, so a 500 reached the browser
  with no `Access-Control-Allow-Origin` at all. The browser could not read
  the `INTERNAL_ERROR` envelope the API had built and reported an opaque
  "Failed to fetch" instead — the one response a client most needs to read
  was the one it could not see. `errors.py` now applies the grant itself, and
  still refuses it for an origin that is not on the allowlist.
- **The Approvals queue did not say what it was asking you to approve.** The
  table showed the document code (`REQ-…`, `PO-…`) and nothing else, so the
  type of document had to be inferred from a code prefix, in a queue that
  mixes requisitions, purchase orders and AI action requests. Approving a
  purchase order and approving a requisition are different acts. There is now
  a **Type** column.
- **The Postgres-backed test that checks cross-PO invoice lines never reached
  the check it was written for.** `POST /purchase-orders/{id}/invoices` runs
  two gates in order: the PO's state, then whether each cited line belongs to
  that PO. The test asserted `INVOICE_LINE_NOT_ON_PO` against a freshly
  created PO, which is `draft`, so the state gate answered first and the test
  failed on the wrong thing. The equivalent SQLite-tier test approves and
  sends the PO first for exactly this reason. Both gates are now asserted, in
  the order they run.
- **The committed OpenAPI YAML was stale and ungated.** `api/openapi.yaml`
  had 80 of its 84 paths disagreeing with `api/openapi.json` — it predated
  FastAPI 0.162.0's `additionalProperties: true` on plain-object response
  models — and nothing regenerated or checked it, while a documentation page
  described it as "generated at build". `scripts/generate_openapi.py` now
  writes both copies from a single `app.openapi()` call, so they cannot
  disagree with each other, and CI regenerates and diffs both.
- **The Playwright suite could silently test the wrong application.** The
  config and the `dev` script both hardcoded port 3000, with
  `reuseExistingServer: !process.env.CI` beside it: if anything else was
  already listening on 3000, Playwright reused *it* and reported page-level
  timeouts instead of "the port was taken". The port is now configurable with
  `E2E_PORT`, and `next dev` / `next start` honour `PORT` rather than pinning
  it.
- **Dependency audits are now real CI gates** (README and SECURITY.md already
  claimed they were). `pip-audit --strict` on backend + worker requirements,
  `npm audit --omit=dev --audit-level=high` on the frontend production
  surface. Known accepted risk documented in `frontend/README.md`: `braces`
  GHSA-vfj7-8cjw-p6xm has no upstream patch and is dev/lint-time only.
- **Three weeks of red `main` was one flaky test, not a broken branch.**
  `backend/tests/test_contract_authority.py::test_expiry_roll_uses_the_tenant_timezone`
  asserted `abs((kiritimati - pago_pago).days) <= 1`, but those zones are 25
  hours apart, so their calendar dates legitimately differ by one *or two*
  days. The test failed in the UTC window where UTC+14 has already rolled
  over and UTC-11 has not — and GitHub's scheduled weekly cron landed inside
  it. The assertion is now `1 <= (kiritimati - pago_pago).days <= 2`, and each
  zone's local date is checked against its own offset-shifted date
  (`utc_before`/`utc_after` bracketing, so the test is race-free at UTC
  midnight). Verified against all 24 UTC hours.
- **Three `mypy` errors that SQLAlchemy 2.1 exposes.**
  `backend/app/core/idempotency.py` — `Session.execute` is typed as returning
  a `Result`, which has no `rowcount`; the object it actually returns for DML
  is a `CursorResult`, which does, so the call is now explicitly cast.
  `backend/app/services/price_intel.py` — `Invoice.po_id` is nullable, and the
  type now says so instead of pretending the value is always present.
  `backend/app/routers/spend.py` — `SpendTransaction.supplier_id` is nullable,
  so the supplier-name lookup is guarded.
- **`rq` 3.0.0 compatibility.** The worker is pinned to `rq` 3.0.0. rq 3
  resolves a default connection and then talks to Redis, so the B-41
  regression (a worker constructed without a connection) now surfaces as
  `redis.exceptions.ConnectionError` rather than `AttributeError`. The
  regression test accepts either — the crash is the point, not the exception
  type rq chooses to raise it with. `rq` was also removed from
  `backend/requirements.txt`: the backend never imports it, and a second pin
  is a second version to keep in step for no benefit.

### Changed

- **The CI service containers are digest-pinned, and the gate now covers
  them.** The five images the compose stack runs were pinned to a digest;
  the two the CI jobs run — `redis:7-alpine` for the worker tier and
  `pgvector/pgvector:pg16` for the Postgres tier — were still mutable tags.
  The reason for pinning is the same in both places: a tag is a mutable name,
  so a rebuilt upstream tag silently changes what was tested, and the CI job
  that reported green was not necessarily testing the same bytes as the last
  one. The compose images are pinned through `.env` indirection because a
  developer can override them without editing the compose file; the CI images
  are pinned inline in the workflow, because a CI job has no `.env` and the
  workflow is what names the image.
  `scripts/pin_digests.py --check` — the offline gate CI runs on every push —
  now parses the workflow's `image:` lines as well, and fails on an unpinned
  or malformed digest. The check is deliberately strict: a dynamically
  interpolated image is rejected rather than skipped, because a gate that
  quietly exempts a line is a gate with a hole in it, and the exempt line
  would be the one image that changes without a commit.
  Both pinned digests were verified against the upstream manifest lists and
  the tiers were re-run against the digest-pinned containers: the Alembic
  drill and the 11 Postgres-backed tests on PostgreSQL 16 with pgvector
  0.8.7, and the 38 worker tests on Redis.- **The CI tiers that were never run now run.** The `postgres-tier` and
  `e2e-tier` jobs were `workflow_dispatch`-only, and the single time the
  workflow was dispatched it failed in the `policy` job before reaching any
  test. So the row-level-security, foreign-key and concurrency assertions had
  never passed anywhere, and the Playwright end-to-end workflow had never run
  green. Both tiers now also run on the weekly schedule, and the worker job
  gets a Redis service so the four Redis-backed worker tests stop skipping.
  The Linux Playwright screenshot baseline is committed — only the Windows one
  was, so the suite could not have passed on a Linux runner.
- **Dependabot config repaired (`.github/dependabot.yml`).** The file was
  invalid YAML — the `updates:` key was missing, so Dependabot was reading a
  bare list and the config never loaded. Beyond the syntax, three policy
  faults let the backlog build for three weeks: `open-pull-requests-limit` was
  3–5, so once that many PRs were open Dependabot stopped proposing anything
  (now 10); the `docker` ecosystem does not recurse, so the single `/` entry
  tracked one of five Dockerfiles (now one entry per directory); and the
  `vitest` family had no group, so `@vitest/mocker` — which `vitest` pins to
  an exact version — could never resolve on its own (now a `vitest-stack`
  group covering `vitest`, `@vitest/mocker`, `@vitest/coverage-v8`, `vite` and
  `@vitejs/plugin-react`). Added `python-security` / `python-runtime` /
  `nextjs` / `react-stack` groups and `ignore` rules for updates that can
  never pass CI: `typescript >= 7.0.0` (typescript-eslint supports
  `>=4.8.4 <6.1.0`; TypeScript 7 is the Go-native port) and `@types/node >= 23`
  / `node >= 23-alpine` (the frontend ships on Node 22).
- **TypeScript 5.9.3 → 6.0.3.** Verified end-to-end: typecheck, lint,
  166 vitest tests and a production build all pass.
- **CI actions moved to current majors.** `actions/checkout@v7`,
  `actions/setup-python@v7`, `actions/setup-node@v7`,
  `actions/upload-artifact@v7`, `softprops/action-gh-release@v3`.
- **Python 3.13 → 3.14** across `ci.yml`, `release.yml` and every base image
  (`Dockerfile`, `backend/Dockerfile`, `worker/Dockerfile`,
  `deploy/keycloak/Dockerfile` → `python:3.14-slim`). Every binary dependency
  in the backend and worker requirement sets has a cp314 wheel.
- **Frontend devDependencies refreshed.** `eslint` 10.14.0, `jsdom` 30.1.3,
  `@playwright/test` 1.64.1, `@types/node` 22.20.5 (held to match the Node 22
  runtime), `@testing-library/*` current, `@vitejs/plugin-react` 6.2.1,
  `vite` 8.3.5, `vitest` 5.1.0, `@vitest/coverage-v8` 5.1.0. An obsolete
  `eslint-disable-next-line @next/next/no-img-element` was removed from
  `frontend/app/opengraph-image.tsx` — ESLint 10 flagged it as unused.
- **`api/openapi.json` regenerated** against FastAPI 0.162.0, which now emits
  `additionalProperties: true` on plain-object response models.
- **Public-repo documentation cleanup.** Removed the internal working set from
  the published docs: `docs/00-plan/audit-findings/` (60+ finding registers),
  `SESSION.md`, `SCORECARD.md`, `BUGS.md`, `PRODUCTION_READINESS.md`,
  `REPOSITORY_AUDIT.md`, `MIGRATION_PLAN.md`, and `docs/05-frontend/grade5/`
  working notes. Bugs and features now live in GitHub Issues
  (`.github/ISSUE_TEMPLATE/`); the remaining docs (`README.md`, `ROADMAP.md`,
  `portfolio.md`, `BRAIN.md`, ADRs) were rewritten against live counts —
  386 backend tests, 166 frontend tests, 15 routes, 98 API operations.
- **CI hardening (`.github/workflows/ci.yml`).** Least-privilege
  `permissions: contents: read`, `concurrency` cancel-in-progress,
  docs gate scoped to the surviving files.
- **Release workflow (`.github/workflows/release.yml`).** Pre-1.0 releases
  marked `prerelease: true`.
- **Single-container image (`Dockerfile`).** Runtime base `python:3.12-slim` →
  `3.14-slim`, aligned with `backend/Dockerfile` and CI.

### Documentation

- **`SECURITY.md` no longer claims controls that do not exist.** "Guaranteed
  controls (Definition of Done)" listed object-storage-only uploads, a
  malware-scan hook, OCR sandboxing, a CORS allowlist and CSRF protection —
  none of which is implemented. The page is now split into what the code
  enforces, what is explicitly **not** implemented, and what is the
  deployer's responsibility (TLS, encryption at rest, secret management).
  A public security policy that overstates its own guarantees is worse than
  one that admits what is missing.
  The rewrite then over-corrected in one place: it listed CORS under "not
  implemented", when the API has always had an allowlist-driven CORS
  implementation in `app/core/secheaders.py`. The claim is now accurate in
  the other direction — CORS is enforced, fails closed, and is applied to
  error responses as well as successful ones.
- **The READMEs were rewritten as public documentation.** `README.md`,
  `backend/README.md`, `frontend/README.md`, `worker/README.md`,
  `android/README.md` and `docs/README.md` were internal working documents
  wearing a public hat. They carried the build-phase numbering, the
  `PLANNED / IN DEVELOPMENT / TESTED / PRODUCTION READY` status vocabulary,
  internal ticket IDs (`B-34`, `B-41`, `B-28`, `B-24`), per-product UAT
  matrices and test-evidence columns, internal module file paths, and
  incident narratives — "the service died on boot and no recurring job had
  ever run", "this replaced a grant of `Super Admin` … a leaked environment
  was a fully administrative token". That material belongs in the changelog
  and the ADRs, not on the page a visitor lands on.
  The capability table now describes what the platform *does* rather than
  which router implements it, the internal defect registers are reframed as
  "Current limitations", and the READMEs link to `docs/README.md` — the
  documentation index — instead of to individual working documents.
- **The documentation index and the knowledge map were rewritten.** The
  `docs/README.md` visibility tree and status column are gone, replaced by
  reading-order guides for evaluating, deploying and working on VANTOR.
  `docs/BRAIN.md` keeps the knowledge graph and the reading trails, and now
  describes the corpus in public terms.
- **The link gate now checks links instead of a convention.**
  `scripts/verify_brain_links.py` required the string `BRAIN.md` to appear in
  every markdown file in the repository — it passed while links pointed at
  files that did not exist, and it forced an internal navigation convention
  onto the public landing pages. It is replaced by
  `scripts/verify_doc_links.py`, which checks that every relative link
  resolves, that no document under `docs/` is orphaned from the index, that
  the public READMEs link to it, and that the docs tree still links back to
  its own central index. `scripts/fix_brain_links.py` is now scoped to
  `docs/`, where the convention belongs.
- **Internal identifiers removed from the published docs.** The `(B-34)`,
  `(B-18)` and `(B-13)` ticket references in the operations runbook, and the
  reference to a retired external specification bundle in the roadmap, are
  gone.

### Known accepted risk

- `braces ≤ 3.0.3` (GHSA-vfj7-8cjw-p6xm, high) has no upstream patch and is
  dev/lint-time only. Documented in `frontend/README.md`.

## [0.8.0] - 2026-10-07

### Added

- **Lightweight weekly CI workflow (`.github/workflows/ci.yml`).** Runs once per week (Mondays 05:17 UTC, ~4 runs/month) and on workflow dispatch. Implements fast verification pipeline: secret scanning, config validation, linting (Ruff), typechecking (Mypy + tsc), unit tests (pytest + vitest), and Next.js production build, with modular triggers preserved for future full PR/push expansion.
- **Complete local verification scripts (`scripts/verify_all.ps1`, `scripts/verify_all.sh`).** One-shot offline verification covering all 16 gates: secrets, encoding, brain links, migrations, digests, palette layer, doc counts, backend lint/types/tests, worker lint/tests, frontend types/lint/tests/build.
- **GitHub community standards.** Added `.github/ISSUE_TEMPLATE/bug_report.yml`, `.github/ISSUE_TEMPLATE/feature_request.yml`, and `.github/PULL_REQUEST_TEMPLATE.md`.
- **Instruction-injection prompt sanitizer** in AI gateway grounding pipeline (`backend/app/services/ai_gateway.py`), with regression test coverage.

### Fixed

- **Mypy union type error in `esign.py` (B-48).** Safely handled optional `db.bind` before dialect inspection.
- **PO invoice state validation tests in `test_approvals.py` and `test_matching.py` (B-49).** Ensured purchase orders transition to `approved` and `sent` prior to recording invoices.
- **Notification pagination test determinism on Windows (B-50).** Ensured monotonically increasing timestamps in `_seed_broadcasts`.
- **OpenAPI 3.1 specification contract parity (B-52).** Replaced obsolete placeholder in `api/openapi.yaml` with full generated specification matching `api/openapi.json`.
- **Sourcing quote award gate (B-51).** Enforced `_assert_evaluable` under lock and required evaluated quote status prior to awarding.

## [0.7.0] - 2026-09-30

### Added

- **Passwordless local auth (`AUTH_MODE=local`, default).** The API becomes its own
  issuer - a persisted RSA keypair, RS256 sessions, same verification path as OIDC.
  `POST /api/v1/auth/session` needs no credentials, trading *who may ask for a
  session* for the ability to run with no identity service at all. Keycloak
  (`AUTH_MODE=oidc`) is unchanged and still available. `backend/tests/test_local_auth.py`
  pins both the token's real signature checks and the removal of the old
  `DISABLE_AUTH=1` bypass, which used to hand out a full-Admin actor with no token.
- **Single-container deployment.** Root `Dockerfile` + `deploy/single-container/start.sh`
  build the web app and API into one image with SQLite, for a free-tier, no-managed-database
  deploy. Documented trade-offs: no row-level tenant isolation, no background worker,
  passwordless sign-in.
- **Frontend ↔ API contract test** (`frontend/lib/contract.test.ts`). Statically checks
  every `api(...)` call site against `api/openapi.json`. Caught two missing routes
  (`GET /integrations`, `GET /webhooks/endpoints`) that the Integrations page had been
  calling and failing on since it shipped.
- License changed **AGPL-3.0-or-later → Apache-2.0**. No copyleft obligation on
  modifications; free to use in closed-source or commercial products.

### Removed

- `frontend/public/silent-check-sso.html` and the `keycloak-js` dependency - no longer
  needed now that sign-in does not require an iframe round-trip to an identity provider.

### Fixed

- **Audit chain false positives.** `record_event` selected the newest row by
  `occurred_at DESC, id DESC` while `verify_chain` walked `ASC` - and `id` is a random
  UUID, so two events in the same microsecond made the two orderings disagree and the
  chain report itself broken after nothing but legitimate activity. `occurred_at` is now
  strictly monotonic per tenant, and verification follows `prev_hash → hash` links
  instead of trusting a sort order; this also newly detects forks and removed rows.
- **Sign-in stopped signing people out on tab switch.** The prior renewal loop treated
  any failed refresh attempt as expiry and force-logged-out the session; it now only
  signs out once the token's own `exp` has actually passed.
- **Brand logo not rendering.** `vantor-logo.png` was a 592KB asset routed through the
  Next.js image optimizer at nowhere near its rendered size; resized to match and served
  `unoptimized` as a static asset.

## [0.6.0] - 2026-09-27

### Added

- **`docs/00-plan/BUGS.md` - the bug & risk register.** One live document for every known
  defect, risk and deliberate omission, graded S1 (money, tenant isolation, or a silently
  disabled control) / S2 (wrong answer or stranded user) / S3 (performance, maintainability),
  each with the reason it matters, the fix, and the regression test that fails without it.
  Gated in CI alongside the other required docs.
- **`GET /approvals` and `POST /approvals/{id}/decide`.** Approvals were write-only, so a
  submitted requisition's approvals could never be decided and the requisition could never
  leave `submitted`. Keyset-paginated, approver-role gated, tenant-scoped, and the decision
  syncs the parent document. `ai:*` filings still go through the copilot's own HITL route.
- **`backend/app/services/refs.py`.** One home for tenant-scoped parent checks
  (`require_ref`, `require_refs`, `require_no_cycle`) now that nine `*_id` columns validate
  a parent at write time.
- **`frontend/lib/ai.ts`.** The single SSE implementation: guarded frame parsing, abort on
  unmount, evidence-frame enforcement, and `X-Vantor-Provider-Key` as a header so a BYOK key
  never rides in the JSON body.
- **Copilot approvals panel and provider picker.** The HITL loop the copilot page's own copy
  promises is now reachable, and a caller can choose a provider.
- **`scripts/check_secrets.py`,** now CI-gated and self-testing (16 cases).
- **Route progress indicator.** Added `nextjs-toploader` to give smooth progress bar feedback across client-side page transitions.
- **Sticky enterprise brand header.** Full-width white brand banner pinned stickily at the top of the sidebar (`position: sticky; top: 0; z-index: 20;`).
- **High-contrast pagination & compact table actions.** Custom Prev (Red) and Next (Green) controls and compact action rows.

### Fixed

- **Sidebar unmounting during client-side navigation.** Preserved the outer `<Shell>` layout during route transitions instead of tearing down the layout into the full-page boot splash.
- **10-second development logout loop.** Gated token refreshing so bypass/dev sessions without an active IdP refresh endpoint do not wipe the user's session.

- **Three match-engine dimensions made partial invoicing impossible.** `duplicates` was
  `prior_invoice_count > 0`, so the second invoice of any partially-paid PO was a duplicate;
  `totals` demanded `po_total == inv_total`; `quantities`/`prices` paired lines by index, so a
  reordered invoice compared the wrong lines. `duplicates` is now a genuine double-billing
  test, `totals` is `0 < inv <= po` (over-billing still fails hard), and lines pair by id.
- **Every award recorded zero savings.** The baseline was computed after the losers were
  rejected, so the comparison set was the winner alone. Captured before the flips, in one query.
- **Approval tiers were cleared in arbitrary order.** `pend[0]` off an unordered result let a
  finance approver consume the manager's slot while the comment claimed the tier list enforced
  order.
- **Idempotency was silently disabled on Postgres** for any write whose fingerprint exceeded
  128 characters; the `DataError` was swallowed by the fail-open handler.
- **The AI gateway could never use a key.** `_provider_key` existed but was never called, so
  every non-ollama provider failed while `/ai/providers` advertised it as configured.
- **The budget gate charged the wrong month**, reading `created_at` (raised) rather than the
  ledger's commitment at send time.
- **The spend cube silently under-reported**, inner-joining without a tenant predicate and
  dropping ledger rows whose PO was missing.
- **Quarantined documents stayed searchable**, and `documents.resource_id` was silently
  truncated to a pointer matching no record.
- **The unread feed truncated itself and could dead-end**, reporting `hasMore: false` with rows
  remaining, and shipping `hasMore: true` with no cursor.
- **The notification badge was unbounded** - every broadcast row as a full entity, no limit, on
  a 30s poll. Capped, and `unreadCapped` is reported rather than quietly truncating.
- **The same webhook could fire twice** (no unique constraint on `url`), and N dead endpoints
  pinned the request for 10s × N. Duplicates collapse to `skipped_duplicate`; a 20s budget
  records the rest as `deferred`.
- **The optimizer's explainability was discarded** - the UI read only `.length`, so a share-cap
  violation was invisible on a page whose copy promises a capped split. Reasons, costs and
  violations are now rendered.
- **Price-evaluate reported a reason it never received** (always "no history"), and declared an
  `evaluated` field the server never returns.
- **`/ai/providers` shape did not match its own UI**, so every provider rendered as
  `undefined (not configured)`.
- **The copilot was the only page with no auth gate**, and one malformed SSE frame destroyed an
  otherwise complete answer.
- **`robots.ts` contradicted itself**, claiming nothing was indexable while allowing all and
  publishing thirteen login-walled routes.
- **Mojibake across the product**: every sidebar icon, the theme toggle, the bell, the search
  trigger, the command palette hints and a sitemap comment.
- **The CI secret guard could never pass.** Its pattern appeared literally in the workflow's own
  command line, so it matched itself and exited 1 on every run; it also scanned a stale worktree
  copy under `.kilo/`. Replaced by `scripts/check_secrets.py`, which scans tracked files only and
  self-tests.
- **`mypy` 12 errors to 0**; ruff unused imports cleared; 113 → 141 backend tests, 37 → 48
  frontend tests.

### Changed

- **The worker is no longer an administrator.** Its service account held `Super Admin`,
  `Procurement Admin` and `Procurement Manager` - purely because the contract expiry roll
  required `Super Admin` and the webhook drain required the operations roles. There is now a
  `Service Identity` realm role covering exactly those two operations, granted to the worker
  and to no human, and deliberately not a subset of any human role. The secret behind the old
  grants lives in the environment of two containers, so a leaked environment was a fully
  administrative token. `deploy/keycloak/provision.py` grants exactly one role;
  `tests/test_realm_parity.py` asserts the grant, that no human role includes it, that both
  worker operations still work, and that the administrative ones are refused.
- **"Within 90 days" is now evaluated in the buyer's own timezone.** It used one
  deployment-wide `CONTRACT_TIMEZONE`, which is correct for exactly one customer. A buyer at
  UTC-12 reaches their own 1 January twelve hours before a UTC server does, so the renewal
  notice fired a day early or late - and the tenants of a procurement system are normally in
  different countries. Migration `0023_tenant_timezone` adds `organizations.timezone` (empty
  means "inherit", so upgrading changes nothing); resolution is tenant → `CONTRACT_TIMEZONE` →
  UTC, and an unusable zone at any level falls through rather than stalling the nightly roll.
- Security headers on the web app's **own** responses, in `frontend/next.config.mjs`. The API's
  CSP was on the wrong host: a policy delivered by the API governs documents the API serves, so
  the pages a user reads ran with no CSP at all. Allowed origins are derived from
  `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_KEYCLOAK_URL` rather than hardcoded, and HSTS is emitted
  only when the app is actually served over https.
- `.env.example` ships `AI_PROVIDER=disabled` and `EMBEDDING_PROVIDER=disabled` to match the
  compose profiles, so a fresh clone is honest (UNKNOWN) rather than failing to connect.
- Sidebar now lists all 13 workspaces; Requisitions, the Negotiation simulator and Integrations
  were previously reachable only via the command palette.
- `GET /spend/price-cases` is keyset-paginated like every other list endpoint.

### Fixed

- **`POST /rfqs/{id}/optimize` had no role check at all** - the only endpoint in `sourcing`
  that skipped `_write`. It commits an audit event and returns the allocation that decides who
  wins a buy, so any authenticated tenant member, including a supplier-side or read-only
  account, could enumerate RFQs and harvest that recommendation. Now gated, with tests from
  both sides: five role sets refused (including the empty set, which must fail closed) and
  three admitted.
- **`drain()` defaulted its tenant scope to "every tenant".** The signature was
  `tenant_id: str = ""` and the filter was applied only `if tenant_id:`, so a caller that
  omitted the argument would have sent *every* tenant's queued webhook payloads to *every*
  tenant's registered endpoints. `tenant_id` is now required, and the predicate is part of the
  statement's own where-clause. The tenant-isolation property had no test at all, which is why
  it could be weakened unnoticed; two tests now pin it and both were mutation-checked to
  confirm they fail when the filter is removed.
- `README.md` line 59 carried a stray `lines="` prefix that stopped the "what works today"
  checklist from rendering. The test count in the run-locally block also said 298.
- Three type imprecisions that made a reader's job harder: one name bound to both a tuple and
  a list in mutually exclusive branches of `security.py`; `_claim` annotated as returning
  `object` when it always returns an `IdempotencyKey`; and a CORS dedupe that relied on
  `set.add` returning `None` inside a boolean `or`.

### Audited, no defect found

Recorded so the next reader does not repeat the work:

- **All 137 `select()` calls** in the routers and services were audited for the shape that
  looks correctly filtered but is not tenant-scoped. 133 carry a tenant predicate; of the four
  that do not, three delegate to a correct helper and one was the `drain()` bug above.
  Modify/delete statements were audited the same way and are clean.
- **Money arithmetic** - every division and rounding in the money paths, and the direction of
  each. A non-positive price baseline raises rather than dividing by zero, and the budget check
  takes a row lock on the budget before reading the aggregate, so two concurrent approvals
  cannot both pass.

---

## [0.5.0] - 2026-09-27

### Added - the "10/10" push. This is what moved the scorecard.

- **Every link is now a real foreign key.** 39 constraints across 37 tables,
  enforced at the database, tenant-scoped (`tenant_id, id` composite so no FK can
  cross a tenant boundary even if RLS is misconfigured), and `ON DELETE RESTRICT`
  everywhere (procurement is evidence; a parent with a child is never deletable).
  The migration chain is: `0017` adds `purchase_orders.requisition_id`; `0018`
  moves every "no link" from `""` to `NULL` (the convention foreign keys can
  express); `0019` adds all the FKs `NOT VALID` then `VALIDATE` in the same
  transaction, so a dirty row rolls the whole thing back, or it doesn't ship.
- **CI now gates merge.** push and pull_request are in `on:`, so a review can be
  blocked by test results. The previous `policy` job actively *failed* on push
  and PR.
- **`tests/test_pg_infrastructure.py` + `tests/conftest.py::pg_client`**: real
  Postgres tier - the one thing that can prove RLS, FKs and `VARCHAR` limits all
  hold at once. Skips silently on SQLite; CI has a `postgres` service so it runs.
- **`tests/test_contract_openapi.py`**: response-shape drift caught at the schema
  level. Every property the frontend reads is asserted against the committed
  `api/openapi.json`, so the next contract mismatches surface as a test failure.
- **`baseline_for` per-line caching** (`BaselineCache`) and **one grouped query**
  for `sourcing.comparison` + `approval pending tiers` - three O(N) table reads
  collapsed into bounded work.
- **Budget gate** now reads from `spend_transactions` (kind `commitment`) with
  `created_at` measured at send time, not at PO creation.
- **Approval queue** (`GET /approvals`, `POST /approvals/{id}/decide`), reusing
  the same `decide_approval` used by the copilot - so SoD, tier order and the
  audit trail are enforced identically by both.
- **Optimizer explainability**: the frontend renders per-supplier `reason` +
  `share_bp` + `cost_minor` + the policy violations inline, and clears the plan
  if you switch RFQs.
- **The spent ledger** reports `hasMore` from the *last scanned row* (not the last
  returned row), so a page of already-read rows never reports `false` for a
  cursor that has more.
- **The notification badge** reports `unreadCapped: true` when it discards rows
  during a large-fetch sweep, so the UI can show `50+` rather than a lie.

### Fixed

- **Three match dimensions made partial invoicing impossible.** `duplicates` was
  `prior_invoice_count > 0`, so the second invoice of any partially-paid PO was
  a duplicate; `totals` demanded `po == inv`; `quantities`/`prices` compared
  lines by index. Now: a real double-billing test, `0 < inv <= po` (over-billing
  still fails hard), and line pairing by `po_line_id` with an index fallback.
  Partial invoicing is CLEAN. Over-billing is still caught.
- **Award records were always zero** because the baseline was computed after all
  the losers were flipped to `rejected`, leaving the winner alone to compare
  against. Baseline is captured in one query **before** any status flips.
- **Approval tiers were cleared in arbitrary order** (`pend[0]` off an unordered
  result). Ordered by tier then timestamp now.
- **Idempotency was silently disabled on Postgres** for any write whose
  fingerprint exceeded 128 chars; the `DataError` was swallowed by the fail-open
  handler. `key` widened to 512 and the fingerprint hashes, so two long paths
  cannot collide anymore.
- **AI providers never authenticated** because the per-request key never
  reached the provider and the environment key fallback chain never called it.
  `/ai/providers` is now honest ({name, configured, needsKey, active}) so the
  frontend stops rendering `undefined (not configured)`.
- **One bad SSE frame destroyed a good answer.** The copilot's parse step now
  guards `JSON.parse`, keeps the complete answer, surfaces `notes` and
  `requires_human_review`, batches deltas, and calls `reader.cancel()` on leave
  - plus the new evidence-frame-enforcement assertion: a stream that ends
  without an evidence frame is not an answer.
- **`/ai/providers` no longer emits a shape the copilot read as objects**,
  the copilot has an auth gate like every other page, and **nav now has all 13
  destinations** (Requisitions, Negotiation simulator, Integrations were
  palette-only).
- **`price-cases` pagination**, **documents quarantine leak**,
  **`documents.resource_id` truncation → 422**, **concurrent price evaluation
  could 500**, **budget gate charged the wrong month**.
- **The CI secret guard could never pass** - its pattern appeared literally in
  the workflow command. Replaced by `scripts/check_secrets.py`, which scans
  tracked files only, and self-tests on 16 strings including an assertion it
  does not flag its own source.

### Verification

- `python -m pytest backend/tests -q` → **155 passed, 2 skipped** (pg-tier skipped
  until `PG_TEST_DATABASE_URL` is set)
- `python -m mypy backend/app --ignore-missing-imports` → clean
- `npm run typecheck` / `npm run lint` / `npm test` / `npm run build` → all green
- `python scripts/check_mojibake.py` (532 files, 19 self-tests) → clean
- `python scripts/check_secrets.py` (539 tracked, 16 self-tests) → clean
- `python scripts/verify_brain_links.py` → 86/86
- `api/openapi.json` regenerated, no drift
- `alembic upgrade head` renders the full FK chain cleanly; DDL checked for the
  absence of `DROP TABLE` / real `UPDATE` rows.

---

## [0.4.0] - 2026-09-26

### Fixed - a green badge that was not green

- **The test suite collected zero tests.** `backend/tests/test_global_parity.py` shipped with an
  `IndentationError`, so `pytest` aborted at collection and exited non-zero while the README, ROADMAP
  and CHANGELOG all reported a passing suite. CI is weekly-only with no PR trigger, so nothing caught
  it. Fixed; the suite is now **96 passing**, and `test_contract_signoff` (previously uncollectable)
  runs again.
- **47 open Dependabot alerts → 0.** Two critical Next.js RCEs, six high-severity `cryptography`
  advisories, and a set of DoS/token-forgery issues in `PyJWT` and `python-multipart`. Bumped
  `next` 14.2.35 → 16.3.6, `react` 18.3.1 → 19.3.0, `postcss` → 8.5.28 (pinned via `overrides`),
  `cryptography` 44 → 50.0.1, `PyJWT` 2.10.1 → 2.15.0, `python-multipart` 0.0.20 → 0.0.32,
  `pytest` 8.3.4 → 9.1.1, `pytest-asyncio` 0.24 → 1.4.0.
- **Added `.github/dependabot.yml`**, which did not exist - so there was no version-update PRs and no
  scheduled scanning at all. Now covers pip (backend, worker, root) and npm (frontend) and GitHub
  Actions, weekly, with security packages grouped.
- **`npm run lint` did nothing.** `next lint` was declared with no ESLint installed and no config, so
  four `eslint-disable` comments were inert and dead code passed "typecheck". Now ESLint 9 with a flat
  config, and `lint` is a real gate in CI.
- **`POST /documents/{id}/extract` had no role check.** Any authenticated tenant member - including
  `Read Only` - could trigger extraction, which mutates document status and rewrites chunk rows.
  Now gated by the same `_write()` roles as upload, and returns 200 (not 201) because a quarantine is
  a real outcome, not a created resource.

### Fixed - security holes SQLite could not see

- **Idempotency was silently broken in production.** `core/idempotency.py` opened sessions with a raw
  `get_session_factory()()`. On Postgres the RLS `WITH CHECK` on `idempotency_keys` rejects the
  insert, and a broad `except` swallowed the error - so replay protection did nothing while tests
  passed on SQLite. Both sites now use a new `core.tenant.pinned_session()` helper.
- **Streamed AI completions were never audited.** The same raw-session bug in `routers/ai.py` meant
  `AI_COMPLETED` inserts were rejected by the `audit_events` RLS policy and discarded by
  `except: pass`. Now pinned, and the failure path rolls back explicitly instead of swallowing.
- **`test_no_unpinned_sessions_outside_request_cycle`** added: scans the source for unpinned
  `get_session_factory()()` calls and fails the build. This is asserted structurally because the test
  database has no RLS and therefore cannot express the invariant.
- **Approval resource overflow → 500.** `approvals.resource` is `String(32)` but the HITL tool writes
  `ai:<caller-supplied resource>`; a 30-character resource overflowed the column on Postgres. Now
  validated to a 422 with a length bound, and the column widened to 64 (migration `0015`).
- **Notification read state was shared, not per-recipient.** A broadcast row (`user_sub=""`) is one
  row seen by the whole tenant, so the first person to click "mark read" silenced the alert for
  everyone. Added a `read_by` JSON column for per-recipient broadcast state.
- **`notifications.read_at` had zero headroom** - `String(32)` storing an `isoformat()` value that is
  exactly 32 characters. Any format change was one commit from a 500. Widened to 40.
- **Notification cursors were tenant-scoped but not user-scoped**, letting a caller page relative to
  another user's row. The cursor lookup now requires the row be visible to the caller.

### Fixed - numbers the product got wrong

- **Cross-currency totals.** `GET /spend/summary` summed minor units across every currency and the
  dashboard formatted the result with whichever supplier sorted first. The API now returns
  `byCurrency` breakdowns plus `currencyCount`, and the UI renders one card per currency instead of a
  meaningless combined figure. Pinned by `test_summary_never_sums_across_currencies`.
- **The should-cost calculator always 422'd.** Its defaults were `overhead=1500` / `margin=1000` in
  fields documented as percentages, producing 150000 basis points against a `le=10000` bound. The form
  could not succeed without being edited first. Defaults corrected and the bound is now checked
  client-side with an explanatory message.
- **"Open RFQs" was a 5-row sample counted and labelled as a total.** Now fetched per status with an
  exact count (and `100+` above the cap).
- **"Contracts expiring ≤90d" was not a 90-day window.** The backend filters on a *stored* status set
  by the expiry roll. Relabelled to what it actually is, with a note.
- **The alerts page claimed "Polls every 30s" and did not poll.** It now polls, and the filter
  re-queries the server rather than hiding rows client-side.
- **Document upload read `process.env` directly**, producing `undefined/api/v1/documents` when the
  variable was unset, while every other call fell back to localhost. Now uses the shared `API_URL`.
- **The copilot's SSE request sent no `Authorization` header** and would have 401'd on every prompt.

### Added - write paths (the UI was read-only)

Previously 16 of 75 API operations were reachable from a browser. Now roughly 30:

- **Sourcing:** create RFQ, advance status, record quotes, compare, award (server-computed totals).
- **Purchase:** create PO, approve, send, receive goods, record invoice, approve after 3-way match.
- **Suppliers:** create, with search / sort / cursor paging against the API.
- **Documents:** upload, extract text, keyword search across extracted chunks.
- **Governance** (new page): audit trail with hash prefixes, live chain verification, categories,
  catalog items, and budget ceilings - the budget gate is now reachable without curl.
- **Copilot:** real SSE frame consumer, provider status readout, and an explicit note that the
  response arrived complete rather than token-streamed.

### Added - shared UI primitives

`DataTable`, `Pager`, `StatCard`, `Skeleton`, `LiveRegion` and `useBoot` replace the hand-written
copies that had drifted: the cursor pager existed 4×, the Keycloak boot 5× (with divergent error
copy), the raw grid 9× and the stat card 8×. `useBoot` also fixes a real bug - the previous boot
blocks called `kc.init()` twice under `reactStrictMode`.

### Added - accessibility and resilience

- Table captions, `scope="col"`, and `aria-sort` on the active sort column (previously glyph-only).
- `aria-live` regions for async results; the copilot transcript is a `role="log"`.
- `aria-modal`, `aria-controls` and `aria-activedescendant` on the command palette; nav matches are
  derived rather than stored, removing a setState cascade.
- `error.tsx`, `loading.tsx` and `not-found.tsx` route boundaries - none existed.
- `sr-only` utility and labelled skeletons (`aria-busy` + status role).

### Added - SEO and discoverability

- Per-route `title` / `description` / `canonical` via server wrappers; root template `%s · VANTOR`.
- `SoftwareApplication` + `Organization` JSON-LD with the real feature list, AGPL licence and
  `offers: 0` (free and self-hosted, not a priced SaaS).
- Social card generated at build time as a real 1200×630 PNG via `next/og` - the previous
  `openGraph.images` pointed at an SVG, which Slack, LinkedIn and X do not render.
- Generated `icon` (32) and `apple-icon` (180) PNGs, plus a web app manifest with shortcuts.
- The real VANTOR brand set shipped to `public/`; `public/logo.svg` was the Digi Tracks company mark.
- Indexing posture made honest: every route is behind OIDC, so `robots` is `noindex` and the sitemap
  uses a build-time `lastModified` instead of a frozen, lying date.

### Changed

- **License: Apache-2.0 → AGPL-3.0-or-later** © 2026 Digi Tracks.
- Frontend: Next.js 14 → 16, React 18 → 19, TypeScript 5.6 → 5.9. Build, typecheck and lint green.
- `GET /spend/summary` gains `byCurrency`, `currencies` and `currencyCount`.
- `POST /documents/{id}/extract` returns 200 instead of 201.
- CI gates: `pip-audit --strict` (backend + worker), `npm audit --audit-level=high`, frontend `lint`,
  and `git diff --exit-code api/openapi.json` so contract drift fails the build.
- Docker: `npm ci` no longer falls back to `npm install`, so CI and production cannot diverge.
- `docs/01-product/portfolio.md` added as the canonical list of the **10** products; every index,
  README and roadmap now points at it. `masterdoc.md` carries a scope note explaining that its
  "five repositories" is the audit scope, not the product count.

## [0.1.0] - 2026-09-25 - Docs-first scaffold [PLANNED]

### Added
- Public repo skeleton: README, LICENSE (Apache-2.0), SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, `.env.example`, `.gitignore`, `docker-compose.yml` (free stack), CI workflow
- Prerequisite docs: requirements, system/domain/database/api, AI (arch/safety/eval), security (arch/threat-model), design-system, brand/logo, android strategy, deployment, runbook, ADRs
- `docs/00-plan/REPOSITORY_AUDIT.md`, `MIGRATION_PLAN.md`, `ROADMAP.md`
- Vantor identity pack: logo/mono/dark/favicon/app-icon/social SVGs
- Module placeholders: `backend/ frontend/ worker/ android/ api/`

### Not yet implemented
- Auth, tenancy, DB migrations, procurement core, document pipeline, Copilot, Android app, prod hardening
