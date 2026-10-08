<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# Changelog - VANTOR

All notable changes tracked here. Statuses: `PLANNED / IN DEVELOPMENT / IMPLEMENTED / TESTED / PRODUCTION READY`.

## [Unreleased]

### Changed

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
  `actions/checkout@v5`, docs gate scoped to the surviving files.
- **Release workflow (`.github/workflows/release.yml`).** `checkout@v5`,
  Python 3.13, pre-1.0 releases marked `prerelease: true`.
- **Dependabot (`.github/dependabot.yml`).** Removed the dead root `pip` entry
  (no requirements file at root), added `docker` ecosystem for base images,
  clarified the Next.js group.
- **Single-container image (`Dockerfile`).** Runtime base `python:3.12-slim` →
  `3.13-slim`, aligned with `backend/Dockerfile` and CI.

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
