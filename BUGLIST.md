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

### B-05 · `alembic upgrade head` fails on SQLite · **OPEN — found 2026-09-28, not yet fixed**

**This is the most serious open item and it is a real, reproduced failure.**

```
$ DATABASE_URL=sqlite:///./_smoke.db python -m alembic upgrade head
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) near "EXTENSION": syntax error
[SQL: CREATE EXTENSION IF NOT EXISTS vector]
```

`0022_pgvector_embeddings.py` has **no dialect guard at all**. Four statements in it are
PostgreSQL-only and will fail on any other engine:

| Line | Statement | Why it breaks off-Postgres |
|---|---|---|
| 80 | `CREATE EXTENSION IF NOT EXISTS vector` | no such syntax; the reported failure |
| 99 | `json_typeof(embedding)` | SQLite's JSON1 has `json_type`, not `json_typeof` |
| 100 | `json_array_length(embedding)` | PostgreSQL-only |
| 121 | `USING hnsw (embedding vector_cosine_ops)` | HNSW is a pgvector access method |

Why it was never caught: **the test suite does not run migrations.** Every test builds its
schema with `Base.metadata.create_all`, and `scripts/audit_migrations.py` only *imports* the
migration modules. So the entire chain has never been executed end to end on any dialect in
this environment, on either engine. The CI PostgreSQL job does run the chain, so Postgres is
probably fine — but that is an inference, not a verification performed here.

The fix is straightforward and safe: guard the four statements on
`op.get_bind().dialect.name == "postgresql"`. On other engines the column stays `JSON`, which is
**exactly** what the model renders there — `app/models/vectortype.py::Vector.load_dialect_impl`
returns `sa.JSON()` for any non-PostgreSQL dialect, and `app/models/document.py` already declares
`embedding` as `nullable=True, default=None`. So a dialect-guarded skip is consistent with the
model rather than a silent lie.

**Untested beyond 0022:** 0023 was never reached. Other migrations may hold further
engine-specific SQL, and the SQLite path is unverified end to end. Fix 0022, then run the chain
on SQLite to find out.

### B-06 · The RLS test covers only the baseline migration · **OPEN**

`tests/test_tenant_isolation.py::test_baseline_migration_defines_rls_policies` asserts that
`0001_baseline.py` defines its policies. It does. But **13 further migrations** — `0002` through
`0014` — each also run `ENABLE ROW LEVEL SECURITY` and `CREATE POLICY tenant_isolation`, and
**no test covers any of them.**

The consequence is the S1 one: a *new* tenant table added in a future migration would ship with
no row-level security, and the suite would stay green. The isolation backstop that
`SECURITY.md` and the runbook both present as mandatory is enforced for a subset of the schema
and unchecked for the rest.

The fix is a structural test, not a PG connection: parse every migration in
`alembic/versions/`, collect the tables each one creates, and assert that every table created
anywhere has a corresponding policy — or is on a small, explicit allowlist of tables that
legitimately have none.

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

### B-27 · Pre-existing ESLint warnings · **OPEN**

`npm run lint` reports 0 errors and 5 warnings. Not introduced by the remediation work and not
yet cleared.

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
- The full application is exercised by **313 passing tests** with no mocks in the auth or money
  paths — every API test mints a real RS256 JWT and verifies it through the real JWKS path.
- The frontend **typechecks, lints with 0 errors, builds**, and its 106 tests pass.
- Every repository guard passes: migrations linear at 23, secrets, encoding, brain links, doc
  counts, palette audit.

**Not proved, and one known break:**

- The app has **not** been run as a composed system. There is no Docker engine, so
  `docker compose up` could not be executed.
- `GET /api/v1/ready` correctly returns **503** on an unmigrated database — the app reports it is
  not ready rather than lying, which is the intended behaviour.
- **`alembic upgrade head` currently fails on SQLite** (B-05). The test suite is unaffected
  because it builds its schema with `create_all` rather than running migrations, which is
  precisely why this went unnoticed.

So: the application code runs, and it is well covered by tests. The migration chain on a
non-PostgreSQL engine does not, and that is the first thing to fix.
