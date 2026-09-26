<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# Changelog — VANTOR

All notable changes tracked here. Statuses: `PLANNED / IN DEVELOPMENT / IMPLEMENTED / TESTED / VERIFIED / PRODUCTION READY`.

## [Unreleased] — 2026-09-26

### Fixed — a green badge that was not green

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
- **Added `.github/dependabot.yml`**, which did not exist — so there was no version-update PRs and no
  scheduled scanning at all. Now covers pip (backend, worker, root) and npm (frontend) and GitHub
  Actions, weekly, with security packages grouped.
- **`npm run lint` did nothing.** `next lint` was declared with no ESLint installed and no config, so
  four `eslint-disable` comments were inert and dead code passed "typecheck". Now ESLint 9 with a flat
  config, and `lint` is a real gate in CI.
- **`POST /documents/{id}/extract` had no role check.** Any authenticated tenant member — including
  `Read Only` — could trigger extraction, which mutates document status and rewrites chunk rows.
  Now gated by the same `_write()` roles as upload, and returns 200 (not 201) because a quarantine is
  a real outcome, not a created resource.

### Fixed — security holes SQLite could not see

- **Idempotency was silently broken in production.** `core/idempotency.py` opened sessions with a raw
  `get_session_factory()()`. On Postgres the RLS `WITH CHECK` on `idempotency_keys` rejects the
  insert, and a broad `except` swallowed the error — so replay protection did nothing while tests
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
- **`notifications.read_at` had zero headroom** — `String(32)` storing an `isoformat()` value that is
  exactly 32 characters. Any format change was one commit from a 500. Widened to 40.
- **Notification cursors were tenant-scoped but not user-scoped**, letting a caller page relative to
  another user's row. The cursor lookup now requires the row be visible to the caller.

### Fixed — numbers the product got wrong

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

### Added — write paths (the UI was read-only)

Previously 16 of 75 API operations were reachable from a browser. Now roughly 30:

- **Sourcing:** create RFQ, advance status, record quotes, compare, award (server-computed totals).
- **Purchase:** create PO, approve, send, receive goods, record invoice, approve after 3-way match.
- **Suppliers:** create, with search / sort / cursor paging against the API.
- **Documents:** upload, extract text, keyword search across extracted chunks.
- **Governance** (new page): audit trail with hash prefixes, live chain verification, categories,
  catalog items, and budget ceilings — the budget gate is now reachable without curl.
- **Copilot:** real SSE frame consumer, provider status readout, and an explicit note that the
  response arrived complete rather than token-streamed.

### Added — shared UI primitives

`DataTable`, `Pager`, `StatCard`, `Skeleton`, `LiveRegion` and `useBoot` replace the hand-written
copies that had drifted: the cursor pager existed 4×, the Keycloak boot 5× (with divergent error
copy), the raw grid 9× and the stat card 8×. `useBoot` also fixes a real bug — the previous boot
blocks called `kc.init()` twice under `reactStrictMode`.

### Added — accessibility and resilience

- Table captions, `scope="col"`, and `aria-sort` on the active sort column (previously glyph-only).
- `aria-live` regions for async results; the copilot transcript is a `role="log"`.
- `aria-modal`, `aria-controls` and `aria-activedescendant` on the command palette; nav matches are
  derived rather than stored, removing a setState cascade.
- `error.tsx`, `loading.tsx` and `not-found.tsx` route boundaries — none existed.
- `sr-only` utility and labelled skeletons (`aria-busy` + status role).

### Added — SEO and discoverability

- Per-route `title` / `description` / `canonical` via server wrappers; root template `%s · VANTOR`.
- `SoftwareApplication` + `Organization` JSON-LD with the real feature list, AGPL licence and
  `offers: 0` (free and self-hosted, not a priced SaaS).
- Social card generated at build time as a real 1200×630 PNG via `next/og` — the previous
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

## [0.1.0] — 2026-09-25 — Docs-first scaffold [PLANNED]

### Added
- Public repo skeleton: README, LICENSE (Apache-2.0), SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, `.env.example`, `.gitignore`, `docker-compose.yml` (free stack), CI workflow
- Prerequisite docs: requirements, system/domain/database/api, AI (arch/safety/eval), security (arch/threat-model), design-system, brand/logo, android strategy, deployment, runbook, ADRs
- `docs/00-plan/REPOSITORY_AUDIT.md`, `MIGRATION_PLAN.md`, `ROADMAP.md`
- Vantor identity pack: logo/mono/dark/favicon/app-icon/social SVGs
- Module placeholders: `backend/ frontend/ worker/ android/ api/`

### Not yet implemented
- Auth, tenancy, DB migrations, procurement core, document pipeline, Copilot, Android app, prod hardening
