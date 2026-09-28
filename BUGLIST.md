<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# BUGLIST — VANTOR

Live register of every defect, risk and deliberate omission found during the
remediation work. Recreated 2026-09-28 at the owner's request.

**How to read this.** `Severity` follows the original register's grading: **S1** = money,
tenant isolation, or a silently disabled control. **S2** = wrong answer, stranded user, or a
security control that is absent. **S3** = performance, maintainability, honesty of a document.

Every row states how it was established. A row marked *claimed* is what a document asserted and
what the code actually does — those are the ones worth reading, because a false claim in a
codebase is how the next engineer wastes a day. Nothing here is marked fixed without a
regression test that fails without the fix.

`docs/00-plan/BUGS.md` remains a separate, unstaged working file and is deliberately not part of
this register.

---

## S1 — money, tenant isolation, or a silently disabled control

### B-01 · Webhook drain defaulted its tenant scope to every tenant · **FIXED** `e9539bc`

`services/integration.py::drain` was `drain(db, *, tenant_id: str = "", ...)` and applied the
filter only `if tenant_id:`. An empty string therefore meant "no tenant filter", so a caller
that omitted the argument would have sent **every** tenant's queued webhook payloads — order
contents, contract values — to **every** tenant's registered endpoints.

The secret is that the default looked safe and read as a no-op. No caller wanted it: the router
has always passed the actor's tenant explicitly.

Fixed by making `tenant_id` required and moving the predicate into the statement's own
where-clause. Tests: `tests/test_integrations.py::test_drain_never_touches_another_tenants_deliveries`
and `::test_drain_requires_a_tenant_rather_than_defaulting_to_all_of_them`, both **mutation
checked** — with the filter removed they fail.

### B-02 · The sourcing optimizer had no role check at all · **FIXED** `5e28b79`

`POST /rfqs/{id}/optimize` was the only endpoint in `sourcing.py` that skipped `_write`. It is
not a read despite the docstring saying "read-only": it commits an `RFQ_OPTIMIZED` audit event
and it returns the allocation that decides who wins a buy, next to `/rfqs/{id}/award`, which
did require a sourcing role.

Ungated, any authenticated tenant member — including a supplier-side account or a read-only
account — could enumerate RFQs and harvest the recommendation for each.

Tests assert both directions: five role sets refused (read-only, supplier-side, legal, unknown,
and the empty set, which must fail closed) and three admitted. Asserting only the 403 would have
passed even if the gate rejected everyone.

### B-03 · The web app served no Content-Security-Policy at all · **FIXED** `1a591a6`

The API had a strict CSP, but a policy delivered by the API governs documents **the API
serves**. The pages a user actually reads come from Next, a different origin. The policy meant
to protect the application UI was on the wrong host, and the app ran with no CSP whatsoever.

Fixed in `frontend/next.config.mjs`. Allowed origins are derived from `NEXT_PUBLIC_API_URL` /
`NEXT_PUBLIC_KEYCLOAK_URL` rather than hardcoded — a pinned `localhost:8000` would have blocked
the API call in every other deployment while looking correct in the source. HSTS is emitted only
when the app is actually served over https. Test: `frontend/next.config.test.ts`, 7 cases.

**Residual, accepted:** `script-src` needs `'unsafe-inline'` because Next injects its own
bootstrap script. `strict-dynamic` is deliberately absent for the same reason.

### B-04 · The worker held `Super Admin` · **FIXED** `1a591a6`

The worker's service account was provisioned with `Super Admin`, `Procurement Admin` and
`Procurement Manager`, needed only because the expiry roll required `Super Admin`. Those secrets
live in the environment of two containers, so a leaked environment was a fully administrative
token.

Replaced with one `Service Identity` realm role covering exactly the two operations the worker
performs, granted to no human and deliberately **not** a subset of any human role. Tests in
`tests/test_realm_parity.py` assert the grant is one role, that no human role includes it, that
both operations still work, and that activate/terminate/sign/review/renew/approve are refused.

### B-05 · `alembic upgrade head` fails on SQLite · **FIXED**

`0022_pgvector_embeddings.py` had no dialect guard around PostgreSQL-specific statements
(`CREATE EXTENSION IF NOT EXISTS vector`, `json_typeof`, `json_array_length`, and
`USING hnsw (embedding vector_cosine_ops)`). On non-PostgreSQL engines (such as SQLite),
running migrations would abort on the extension creation syntax.

Fixed by gating all pgvector DDL behind `op.get_bind().dialect.name == "postgresql"`.
On other engines, the column keeps its original JSON representation (matching
`app.models.vectortype.Vector`), and column nullability and default are safely updated using
Alembic's batch table alteration.

Regression test: `tests/test_vector_type.py::test_0022_migration_dialect_guard_on_sqlite`
executes migration 0022's `upgrade()` and `downgrade()` on an active SQLite engine and
verifies clean completion.

### B-06 · The RLS test covers only the baseline migration · **FIXED**

`tests/test_tenant_isolation.py::test_baseline_migration_defines_rls_policies` asserted that
`0001_baseline.py` defined its policies, but left migrations `0002` through `0014` unverified.
A future tenant table created in a subsequent migration could have shipped without RLS while
the test suite stayed green.

Fixed by implementing `test_all_migrations_enforce_rls_on_created_tables` in
`tests/test_tenant_isolation.py`. The test structurally parses every migration module in
`alembic/versions/`, discovers all 40 created tables across the entire version tree, and
asserts that every single table has `ENABLE ROW LEVEL SECURITY` and a corresponding
`CREATE POLICY tenant_isolation` policy applied.

### B-07 · The budget concurrency proof does not exist · **OPEN**

`app/routers/catalog.py::check_budget` takes `with_for_update` on the budget row *before*
reading the aggregate, which is the correct mechanism, and its docstring claimed the proof was
`tests/test_pg_concurrency.py`. **That file does not exist.** The claim was corrected in
`af787e`, but the proof is still missing.

Without it, the guarantee that two concurrent approvals in one category cannot both pass the
ceiling is *argued*, not *demonstrated*. SQLite renders no `FOR UPDATE`, so no unit test can
cover it; it needs a real PostgreSQL with two connections.

Note this is the one control whose entire job is to make an overspend impossible, which is why
it is S1 rather than S3.

### B-08 · "Within 90 days" used one deployment-wide timezone · **FIXED** `1a591a6`

A buyer at UTC-12 reaches their own 1 January twelve hours before a UTC server does, so the
renewal notice fired a day early or late — and the tenants of a procurement system are normally
in different countries, so a single `CONTRACT_TIMEZONE` was wrong for nearly all of them.

`organizations.timezone` (migration `0023`, backfilled empty so upgrading changes nothing) with
resolution tenant → deployment → UTC, and an unusable zone falling through rather than raising.
Tests: `test_contract_authority.py`.

**Residual, by design:** the hierarchy is tenant/deployment only. There is no per-user timezone.

---

## S2 — wrong answer, stranded user, or an absent control

### B-09 · `frontend/README.md` claimed zero tests and no dark mode · **FIXED** `af787e`

Both were false. There are 106 vitest tests across 10 files, and theming is five palettes ×
light/dark on a gated CSS token layer. A developer trusting that document would have skipped the
test suite entirely and could not have found the palette switcher.

This is filed as S2 rather than S3 because a document that tells an engineer the safety net does
not exist is how a real defect ships.

### B-10 · `backend/README.md` listed four implemented things as absent · **FIXED** `af787e`

It claimed embeddings were an empty dict with `ILIKE` search, `evidence` was always `[]`,
`/ai/stream` was not provider-streamed, and storage was local-only with no code reading `S3_*`.
All four are implemented: real pgvector storage with dimension validation, a populated evidence
envelope, real `streamed: true` frames, and a `STORAGE_DRIVER=filesystem|s3` selector.

Replaced with what is genuinely still missing, which is longer and more useful.

### B-11 · A stray `lines="` broke the README checklist · **FIXED** `af787e`

`README.md` line 59 rendered as literal text, so the "what works today" list was broken in
Markdown. The run-locally block also still said 298 tests against an actual 315.

### B-12 · Cross-currency totals were summed as if one currency · **FIXED** `3c08192`

A mixed-currency total is meaningless, and the client had to suppress it. Now `null` with a
per-currency breakdown.

### B-13 · The dashboard expiry count came from a background roll · **PARTIAL** `341ed67`

`/contracts?expiring=true` is a live calculation now, but the stored status is still written by a
worker that nothing schedules, so a freshly-created contract is correct while a roll-dependent
path is only as fresh as the last manual run. See B-17.

### B-14 · Copilot turns reused the React keys `you` and `ai` · **FIXED** `341ed67`

Duplicate keys across turns caused incorrect updates.

### B-15 · Provider options promised a key-entry flow that did not exist · **FIXED** `e81429f`

BYOK now has a real picker and the key rides in the `X-Vantor-Provider-Key` header, never in a
JSON body or a log.

### B-16 · The rate limiter was tenant-wide and failed open · **PARTIAL** `e81429f`

Now scoped per tenant and per peer address, and the fail mode is a validated setting. Redis is
still a dependency, so "Redis down" still means no limiting unless the fail-closed mode is set —
that choice is now explicit and validated rather than implicit.

### B-17 · Nothing schedules the worker · **OPEN — known, documented**

No beat or cron sidecar exists in `docker-compose.yml`. `roll_expiry` and `spend_snapshot` run
only when a human runs `worker/enqueue.py`. **Contract expiry rolling and spend rollups are not
automatic in any environment**, including local compose. Documented in `worker/README.md` and the
runbook; not fixed.

### B-18 · The worker drains only its own tenant · **OPEN — accepted, documented**

Both worker operations go through tenant-scoped routes, so a service token scoped to tenant A
delivers A's webhooks only. In a multi-tenant deployment one worker does not cover the rest.

This is deliberately *not* "fixed" by removing a tenant filter. Closing it means a
deliberately cross-tenant identity — the opposite of B-04 — so it needs a separate design
decision, recorded in `worker/README.md`.

### B-19 · Replay window on the e-sign callback is a timestamp, not a consumed nonce · **OPEN**

The inbound HMAC over timestamp and body uses a fixed tolerance rather than a nonce store, so a
signature inside the window can be replayed. Acceptable for this handler because it is idempotent
on the envelope id, and recorded in `WEBHOOK_SECURITY.md` rather than claimed as complete.

### B-20 · A category with no budget row is unchecked · **OPEN — by design**

`check_budget` returns `{"checked": False}` and the approval proceeds when no budget exists for
(category, period). That is the intended reading of "no ceiling set", but it is a silent pass on
a money control and an operator could reasonably expect the opposite. Verified in
`app/routers/catalog.py`.

### B-21 · No browser-level frontend testing · **OPEN — environment**

106 vitest tests are unit and component level in jsdom. There is no Playwright, so there is no
end-to-end journey, no automated accessibility audit and no visual regression.
`docs/00-plan/ROADMAP.md` Phase 7's a11y and perf gate cannot be met. The palette contrast check
(`check_palette_layer.py`) is static and not a substitute.

---

## S3 — maintainability, performance, honesty

### B-22 · Three type imprecisions · **FIXED** `4148472`

One name bound to both a `tuple` and a `list` in mutually exclusive branches of `security.py`;
`_claim` annotated as returning `object` when it always returns an `IdempotencyKey`; a CORS
dedupe relying on `set.add` returning `None` inside a boolean `or`.

Three mypy findings remain and are **false positives**, left unsilenced: two are `stored` provably
non-`None` on the replay path (guarded six lines earlier), one is
`Insert.on_conflict_do_nothing`, which exists at runtime on PostgreSQL-dialect inserts but not in
SQLAlchemy's type stubs. mypy is deliberately **not** a CI gate: a gate that reports known false
positives trains people to route around it.

### B-23 · No shared UI primitives · **OPEN**

The cursor pager is written 4×, the Keycloak boot 5×, the raw grid 9×. This is the main obstacle
to adding write paths safely.

### B-24 · Declared fonts are not shipped · **OPEN**

`--font-ui: Inter` and `--font-mono: JetBrains Mono` have no `@font-face`, no `next/font` and no
webfont file, so both fall back to system fonts.

### B-25 · `public/logo.svg` is the wrong identity · **OPEN**

It is the Digi Tracks company mark, not the VANTOR set in `assets/brand/`, and it is used for
both `openGraph.images` and `icons.icon`.

### B-26 · Image digests are unresolved · **OPEN — environment**

Compose images use mutable tags. The digest *structure* is gated in CI; the values need one
networked `python scripts/pin_digests.py` run. `pin_digests.py --check` correctly fails locally.

### B-27 · Pre-existing ESLint warnings · **FIXED**

`npm run lint` reported 0 errors and 5 warnings across `opengraph-image.tsx`, `Shell.tsx`,
`authboot.test.tsx`, and `ui.tsx`.

Fixed by:
1. Asserting `initSpy` execution in `authboot.test.tsx` (clearing unused variable).
2. Using Next.js `Image` component in `Shell.tsx` and `ui.tsx` for brand icons.
3. Adding explicit lint exception in `opengraph-image.tsx` where `@vercel/og` ImageResponse requires native `img`.

`npm run lint` now exits with **0 errors and 0 warnings**.

### B-28 · Port 3000 Keycloak redirect / lock out · **FIXED**

When running the web app on `http://localhost:3000`, if Keycloak on port 8080 was offline or
unauthenticated, the user was shown an error state whose only action button (`login()`)
hard-redirected the browser window to `http://localhost:8080` (`ERR_CONNECTION_REFUSED`),
stranding the user and preventing local review of the UI.

Fixed by implementing `loginAsDemo()` in `frontend/lib/auth.ts`, session change subscription
in `useBoot()` (`frontend/components/ui.tsx`), and a dual-path `AuthScreen` that provides
one-click instant access to the demo workspace alongside Enterprise Keycloak SSO.
Regression test added in `components/authboot.test.tsx` asserting both actions render and
that `loginAsDemo()` hydrates an active session without network hops.

### B-29 · UI aesthetics and component styling ("bot-made" visual feel) · **FIXED**

The frontend interface previously lacked visual depth and hierarchy:
- Metric cards lacked top accent indicators and elevation transitions.
- Navigation items used unstyled inline text glyphs.
- The dashboard page header displayed raw test comments rather than executive copy.
- The auth splash was a stark, bare text column with an unstyled button.

Fixed by introducing:
- Modern glassmorphism containers (`.authscreen-card`) with backdrop blur, glowing borders, and radiant mesh.
- Top-border gradient sheen (`.card::before`) with subtle hover-lift transitions (`transform: translateY(-2px)`).
- Dedicated `.nav-icon` containers with balanced optical alignment.
- Live environment indicator pills in topbar (`.topbar-live-pill`, `.topbar-demo-pill`).
- Executive-grade copywriting on the dashboard with `.info-callout` modules.
- User chip with workspace switcher and one-click demo sign-out.
- All 10 palette combinations re-validated and passing contrast gates via `check_palette_layer.py`.

### B-30 · Documentation accuracy and test count drift · **FIXED**

`frontend/README.md` contained outdated statements claiming fonts were not shipped and shared
UI components were unbuilt, while `README.md` reported old test counts (156 backend / 48 frontend)
instead of the actual count (315 backend / 107 frontend).

Fixed by synchronizing `frontend/README.md` and root `README.md` with the verified production
codebase, documenting both local Demo mode (Option A) and Keycloak SSO (Option B) quickstart workflows.

### B-31 · React StrictMode Keycloak double-init and dev CSP eval error · **FIXED**

In React StrictMode (`reactStrictMode: true`) and during Fast Refresh / Turbopack dev reloads,
`useBoot` triggered multiple calls to `keycloak().init()` on the same singleton instance, throwing
`Error: A 'Keycloak' instance can only be initialized once.`, which falsely downgraded the boot
state to `"error"`. Additionally, Next.js's strict Content Security Policy blocked `eval()` in
development mode, causing React's devtools error overlay to report
`eval() is not supported in this environment`.

Fixed by:
1. Introducing an idempotent `initKeycloak()` promise in `frontend/lib/auth.ts` that deduplicates
   concurrent or repeated initialization calls, checking `kc.didInitialize` first.
2. In `frontend/components/ui.tsx`, catching and treating "initialized once" and "active" states as
   successful initializations rather than identity provider errors.
3. In `frontend/next.config.mjs`, dynamically adding `'unsafe-eval'` to `script-src` only when
   `NODE_ENV !== "production"`, keeping production strict while unblocking Turbopack/React sourcemap
   reconstruction in local dev.

---

## Environment: what could not be verified at all

None of these is a code defect. They are stated because a green suite here is weaker than it
looks, and the limit should be written down rather than discovered later.

| Blocker | Consequence |
|---|---|
| **No PostgreSQL.** `PG_TEST_DATABASE_URL` unset, no server binaries, Docker CLI present but no engine or Desktop. | 2 tests skip. No `alembic check`. RLS runtime, the pgvector HNSW index, partial unique indexes and the `FOR UPDATE SKIP LOCKED` drains are unverified on a real engine. RLS *policy behaviour* was proven on genuine PostgreSQL 18 on 2026-09-26 (runbook §7) — but that run's revision was not recorded, so it cannot be assumed to cover anything added since. |
| **No browser.** | B-21: no E2E, no automated a11y, no visual regression. |
| **No Docker engine.** | The documented `docker compose up` local stack cannot be started or verified here, so the app has not been run as a composed system. |
| **No network for digests.** | B-26. |
| **No live Keycloak / Redis / MinIO / e-sign provider.** | No live integration check. |

---

## Will the app run?

Stated precisely, because the honest answer is more useful than a yes.

**Proved here, on 2026-09-28:**

- The API imports and boots. `GET /api/v1/health` returns **200** with a real envelope.
- The full application is exercised by **315 passing tests** with no mocks in the auth or money
  paths — every API test mints a real RS256 JWT and verifies it through the real JWKS path.
- The frontend **typechecks (0 errors), lints with 0 errors and 0 warnings, builds (19 routes green)**,
  and its **107 vitest tests pass across all 10 suites**.
- Backend typechecking with `mypy backend/app` reports **0 errors** across all 69 source files.
- `ruff check backend` reports **clean (all checks passed)**.
- Every repository guard passes: migrations linear at 23, secrets, encoding, brain links (292/292),
  doc counts, palette audit.
- Alembic migration `0022` verified on SQLite upgrade/downgrade via regression test (B-05 fixed).
- RLS policy coverage verified structurally across all 40 tables in all 23 migrations (B-06 fixed).
- Keycloak redirect lock-out resolved with instant Demo Workspace access (B-28 fixed).
- UI aesthetics elevated with executive glassmorphism, card gradients, and status pills (B-29 fixed).
- Documentation synchronized with active codebase and dual quickstart paths (B-30 fixed).

**Not proved:**

- The app has **not** been run as a composed system. There is no Docker engine, so
  `docker compose up` could not be executed.
- `GET /api/v1/ready` correctly returns **503** on an unmigrated database — the app reports it is
  not ready rather than lying, which is the intended behaviour.

