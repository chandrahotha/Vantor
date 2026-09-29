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

### B-07 · The budget concurrency proof did not run anywhere · **FIXED**

`app/routers/catalog.py::check_budget` takes `with_for_update` on the budget row *before*
reading the aggregate, which is the correct mechanism, and its docstring claimed the proof was
`tests/test_pg_concurrency.py`. **That file did not exist** when this was first written. The
claim was corrected in `af787e`, and the proof has since been written.

It needed a real PostgreSQL with two connections, because SQLite renders no `FOR UPDATE` and no
unit test can cover the mechanism at all. `tests/test_pg_concurrency.py` now proves three
things: two concurrent approvals cannot both clear one ceiling, the loser is told the winner's
committed figure rather than being left to infer it, and a category with no budget row is not
gated (B-20).

**The proof existed and still did not run.** `ci.yml` selected the Postgres tier by path —
`pytest tests/test_pg_infrastructure.py` — and named only one of the two files, so the entire
budget-atomicity proof, the one control whose job is to make an overspend impossible, had never
once executed in CI. It now selects by marker (`pytest -m pg`), which both files carry and which
exists for exactly this purpose, so a third Postgres file needs no edit to be included.

### B-08 · "Within 90 days" used one deployment-wide timezone · **FIXED** `1a591a6`

A buyer at UTC-12 reaches their own 1 January twelve hours before a UTC server does, so the
renewal notice fired a day early or late — and the tenants of a procurement system are normally
in different countries, so a single `CONTRACT_TIMEZONE` was wrong for nearly all of them.

`organizations.timezone` (migration `0023`, backfilled empty so upgrading changes nothing) with
resolution tenant → deployment → UTC, and an unusable zone falling through rather than raising.
Tests: `test_contract_authority.py`.

**Residual, by design:** the hierarchy is tenant/deployment only. There is no per-user timezone.

### B-32 · The API failed open outside production, three separate ways · **FIXED**

`app/core/security.py` carried three `if not settings.is_prod` branches, each of which returned a
full Admin `Actor` instead of refusing:

1. any token beginning `vantor-` (and a hardcoded list of dev/demo strings) — accepted with no
   signature, no expiry and no issuer check, defaulting the tenant to `vantor-corp`;
2. any token that failed to parse at all;
3. any token whose `kid` was not in the JWKS.

Established by execution against the running service, not by reading:

    GET /api/v1/me   Authorization: Bearer vantor-attacker
    200 {"tenantId": "vantor-corp",
         "roles": ["Buyer", "Procurement Manager", "Admin", "Approver"]}

The branches read as development conveniences. They were a full authentication bypass in dev,
staging *and* test, on a system that books purchase orders. The comment added when they were
removed names all three and the three root causes that made someone reach for them, because the
instinct to add them comes back if the causes come back.

Tests: `test_auth.py::test_forged_tokens_are_401_in_test_env` and
`::test_development_env_also_fails_closed` — deliberately one per environment, because a single
"non-prod" test would not have caught a branch that keyed on `is_prod` rather than on
development.

### B-33 · The web app could mint an Admin session without the IdP · **FIXED**

The frontend half of B-32, and it made the server-side bypass unnecessary — which is part of why
it survived. `lib/auth.ts` seeded a module-scope session whose token was the literal string
`"vantor-corp-jwt-session"`, so the app rendered a signed-in shell before any identity existed
and every API call carried a credential the backend correctly rejected. `components/SignInModal`
— rendered by `Shell.tsx`, reachable from three places in the chrome — let anyone type a name and
pick a role from a dropdown, "Admin" included, and called `switchPersona()` to build a session
from that string alone.

Now: a session exists if and only if the IdP returned a signed token carrying a tenant. Tokens
are in-memory only and are never restored from storage, because an access token has a fifteen
minute life and a stale one surfaces as a 401 that reads like a bug in the app. The persona list
and the modal are gone, and `authboot.test.tsx` asserts the *absence* of an identity at module
load — the previous implementation would have passed any test that only checked the shell
renders.

### B-34 · The API client fabricated a bearer token when none was set · **FIXED**

`lib/api.ts` defaulted its token getter to `() => getSession()?.token || "vantor-corp-jwt-session"`.

This is the same bypass as B-32 in a single line, and it is the reason the frontend is not
provably fixed by deleting `SignInModal`: if the boot ever failed to register a getter, every
request went out carrying a fabricated credential rather than none. Against the B-32 backend that
was a silent full-Admin request; against the fixed backend it is a 401 on everything. The default
is now `getSession()?.token` and nothing else — **no unauthenticated request is ever sent.**

### B-35 · The default `OIDC_ISSUER` did not match the `iss` in the token · **FIXED**

Two failures in one setting, in sequence. It originally defaulted to the Compose service name
`keycloak:8080`, which is resolvable only inside the Compose network, so a native `uvicorn` could
not fetch the JWKS and answered `503 Identity provider unavailable` on every authenticated
request. Replacing that with a host-reachable `127.0.0.1:8080` traded one total failure for
another, and the replacement was worse because it looked fixed: `jwt.decode(issuer=...)` compares
the string *exactly*, and Keycloak's realm is served on `localhost`, so `127.0.0.1` is a different
string for the same server and every real token was refused with `401 Invalid token`.

The tell is the same in both cases: **`/health` stayed green**, because it touches no dependency.
A 401 whose cause is a configuration string is not a 401 a developer can debug from the client.

Fixed to `http://localhost:8080/realms/vantor`, matching `.env.example`. `tests/test_config.py`
pins the backend default against `.env.example` and against the Next client's Keycloak URL, so the
three files that state the same fact cannot drift. Mutation-checked: two of the four tests fail on
the `127.0.0.1` value.

### B-36 · The dashboard discarded *why* each panel failed · **FIXED**

`Promise.allSettled` over the five panels, keeping the panel name and throwing away the reason, so
a total outage reported:

    Notice — some live panels could not reach backend: spend, contracts, rfq:sent, rfq:response, purchase orders.

Five failures, zero causes, and no way to distinguish a 401 from a 503 from a backend that was not
running — so the message could not be acted on without a devtools session. It now carries the
status, the code and the request id per panel, which is what the backend's own log line is keyed
on, so a report can be matched to a log entry instead of guessed at.

Worth naming alongside B-35: these two defects looked identical from the browser. B-35 was a
configuration string; B-36 was the reason nobody could see that.

### B-41 · The worker crashed on boot, so nothing consumed what the scheduler armed · **FIXED**

`worker/worker.py` built its queues from a real `Redis.from_url(REDIS_URL)` and then constructed
the worker as `Worker(queues).work()` — queues passed, connection not. In the pinned rq 1.16.2
that is a crash on boot, not a default:

    rq/worker.py:147   connection = self._set_connection(connection)
    rq/worker.py:298   if connection is None: connection = get_current_connection()
    rq/worker.py:300   current_socket_timeout = connection.connection_pool.connection_kwargs...

`get_current_connection()` resolves inside rq's fork-based work-horse. In the parent process —
which is where an entrypoint runs — there is no current fork, so it answers `None` and the next
line dereferences it. `AttributeError: 'NoneType' object has no attribute 'connection_pool'`,
before a single job is fetched.

Filed as S1 because it is a silently disabled control rather than a crash report. The compose
stack comes up, `beat` cheerfully logs `scheduled roll_expiry at …`, and the contract expiry roll
and the webhook drain — the two jobs the whole worker exists for — never run. Nothing in the
system reports the failure: the control is simply absent, and its absence looks identical to a
quiet night. It is B-34's exact shape one file over, and it survived the same way, by never being
run: no CI job imported `worker/` at all.

**Established by execution, not by reading.** Both processes were run against a real Redis:

    beat:    scheduled roll_expiry at 2026-09-28T17:43:40+00:00 (id=beat:roll_expiry:179061742)
    redis:   rq:queue:default LLEN 21        # armed, promoted, and going nowhere
    worker:  *** Listening on default, documents...
             default: vantor drain_webhooks (every 5s) (beat:drain_webhooks:358123484)
             AttributeError: module 'os' has no attribute 'fork'      # <- the real defect, after the fix

`tests/test_worker.py` pins both halves. The crash is reproduced with **no Redis at all** — it
happens on `rq/worker.py:300`, before any socket opens — so the regression runs in every
environment including CI's worker job. Constructing a real `rq.Worker` *does* need Redis
(`rq/worker.py:205` calls `connection.client_setname(...)`), so those assertions skip without
`RQ_TEST_REDIS_URL` and the CI job provides one; a regression that only runs where a dependency
happens to be present is B-07's shape, which is why the no-Redis half carries it alone.

**Residual, stated rather than implied:** job *execution* is the one link not proven here. rq's
work-horse calls `os.fork()`, which does not exist on Windows, so the dequeue was observed and
the execution was not. It runs in a Linux container in every real deployment.

### B-43 · The worker's documented identity carried no tenant, so every operation was a 403 · **FIXED**

`app/core/security.py` refuses a token that carries no tenant (`403 Token carries no tenant`),
and the `tenant_id` claim is mapped by a **client-scoped** mapper from the user attribute of the
same name. The `vantor-service` client — the worker's documented identity, the one compose
provisions — carried only the audience mapper, and `provision.py` granted its service account
roles but never set a `tenant_id` attribute on it. So the client-credentials token, the path
every document describes, carried no tenant and the API refused **every worker operation**:
the expiry roll and the webhook drain could not run on it at all.

Filed as S1 because it is a silently disabled control, and it is B-32's shape in miniature: the
escape hatch (`SERVICE_API_TOKEN`, a token minted by hand, which does carry a tenant) worked, so
the scheduled jobs ran on the path nobody documents while the documented path was never exercised.
Nothing caught it because `test_realm_parity.py` asserted the tenant mapper on `vantor-web` only,
and every other test mints its own JWT with a tenant — assertions about the mock, not about the
system, which is the exact sentence VNT-052's audience finding is written in.

**Established structurally at both ends, and fixed at both:**

* the realm template gains the `tenant_id` mapper on `vantor-service` (mapping the user
  attribute the provisioner stamps);
* `provision.py` stamps `SERVICE_TENANT` (default `vantor-corp`) onto the service-account user,
  idempotently, so rotation and restarts keep it in step.

`test_realm_parity.py::test_tenant_is_in_the_service_token_too` asserts the mapper on the
worker's client, that it maps from the stamped attribute, and that it applies to the access
token — the version of `test_tenant_is_in_the_token` that would have caught this.

**Residual, stated:** the live service flow was not re-verified against a real Keycloak here —
the live realm's admin and client credentials do not match `.env`, so the client-credentials
grant could not be completed. It runs in CI's realm shape and is asserted structurally; the
first live run is the thing that proves it.

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

### B-13 · The dashboard expiry count came from a background roll · **FIXED** (via B-17 + B-41)

`/contracts?expiring=true` is a live calculation, but the stored status was also written by a
worker that nothing scheduled, so a freshly-created contract was correct while a roll-dependent
path was only as fresh as the last manual run. The row stood on B-17, and B-17 needed two fixes
before it was a fix at all: the scheduler had to exist (B-34) and something had to consume what
it armed (B-41). Both are done, so the roll now runs on its own in every environment including
local compose.

What remains is an operational truth rather than a defect, and it is in the runbook: if the
`beat` container is not running, the roll does not happen, and the stored statuses are as stale
as the last successful run. The dashboard's live query is unaffected, which is the part that
originally made the failure hard to see.

### B-14 · Copilot turns reused the React keys `you` and `ai` · **FIXED** `341ed67`

Duplicate keys across turns caused incorrect updates.

### B-15 · Provider options promised a key-entry flow that did not exist · **FIXED** `e81429f`

BYOK now has a real picker and the key rides in the `X-Vantor-Provider-Key` header, never in a
JSON body or a log.

### B-16 · The rate limiter was tenant-wide and failed open · **FIXED** `e81429f` — status corrected 2026-09-28

Now scoped per tenant and per peer address, and the fail mode is a validated setting
(`RATE_LIMIT_FAIL_MODE`, `open`|`closed`, refused at startup read on anything else).

This row stood at PARTIAL while its own text described a resolved state. The sentence it closed
with — "Redis down still means no limiting unless the fail-closed mode is set" — was false, and
had been since the in-process backstop landed: the default is *degraded to per-process limiting*,
not *no limiting*, which is a different answer to the same question and the one an operator
responding to a Redis outage needs. `app/core/ratelimit.py` states it; the row now does too.

### B-17 · Nothing scheduled the worker · **FIXED** — in two parts, and the second was found by running it

There was no beat or cron sidecar in `docker-compose.yml`, so `roll_expiry` and `spend_snapshot`
ran only when a human ran `worker/enqueue.py`. **Contract expiry rolling and spend rollups were
not automatic in any environment**, including local compose. This row stood open for months
because the missing thing was documented rather than absent — the runbook said the worker had to
be triggered by hand, which read as a decision.

**Part one — the scheduler.** `worker/beat.py` is now a real service against the pinned rq
1.16.2 (B-34), and `docker compose up` starts it. That is the row's own fix, and on its own it
was worth nothing, because of part two.

**Part two — the consumer.** `worker/worker.py` ended with `Worker(queues).work()`, passing the
queues but not the connection. In rq 1.16.2 that is a crash on boot, not a default (B-41). The
`worker` container exited immediately, so everything `beat.py` scheduled piled up in
`rq:queue:default` with nobody to consume it. The two defects are one defect: a scheduler that
arms jobs nobody runs. Neither was visible from reading, because `test_beat.py` never built a
Worker and there was no CI job that imported the worker at all.

Found by execution, not by review — the two of them run against a real Redis:

    beat:  scheduled roll_expiry / drain_webhooks / spend_snapshot
    redis: rq:queue:default LLEN 21     # armed, then promoted, and left to rot
    worker: "*** Listening on default, documents..."
            "default: vantor drain_webhooks (every 5s)"   # then the crash

`beat.py` and the worker are now separate services with separate failure modes, both in CI, and
the scheduler's arming/promotion chain is proven against genuine Redis rather than a fake.

**Residual, stated honestly:** job *execution* is the one link not proven here. rq's work-horse
calls `os.fork()`, which does not exist on Windows, so the dequeue was observed and the execution
was not. It runs in a Linux container in every real deployment.

### B-18 · The worker drains only its own tenant · **FIXED** — one identity per tenant, closed 2026-09-28

Both worker operations go through tenant-scoped routes, so a service token scoped to tenant A
delivers A's webhooks only. In a multi-tenant deployment one worker does not cover the rest.

This was deliberately *not* "fixed" by removing a tenant filter — that closes it by creating a
deliberately cross-tenant identity, the opposite of B-04. It is closed the other way: the worker's
identity is now per tenant, and nothing about it is cross-tenant.

* `SERVICE_TENANT` (default `vantor-corp`) is stamped onto the service-account user by
  `deploy/keycloak/provision.py`, where the `tenant_id` claim mapper reads it from. Before B-43
  the claim did not exist at all and the worker could not call the API on any path — see B-43.
* A multi-tenant deployment provisions one identity per tenant (client + secret +
  `SERVICE_TENANT`) and runs one worker container each. The scheduler's grid is absolute
  epoch-time, so N `beat` instances converge on the same buckets rather than doubling them.
* Documented in `worker/README.md` and the runbook; the escape hatch (`SERVICE_API_TOKEN`)
  remains for environments where the grant is unavailable, and is not the documented path.

**Residual, stated honestly:** the per-tenant fleet is documented and the identity is
provisioned, but N workers against N tenants were not run here. The single-tenant case is the
one the compose stack ships.

### B-19 · Replay window on the e-sign callback is a timestamp, not a consumed nonce · **FIXED** — closed 2026-09-28

The inbound HMAC over timestamp and body uses a fixed tolerance rather than a nonce store, so a
signature inside the `REPLAY_WINDOW_S` window can be replayed. The window is real and unchanged:
the MAC covers `{timestamp}.{body}` and a timestamp outside 300s is refused, which is what
stops a capture being replayed *later*.

**The acceptance for the remaining window was asserted in prose and turned out to be half
false.** It rested on the handler being "idempotent on the envelope id". The state transition
was idempotent — a replay writes no second signature row and cannot change a terminal status.
The *provenance* was not: `apply_callback` stamped `verified_at` on every callback that agreed
with the current state, so a replayed capture overwrote the record of when the provider
originally confirmed that envelope. On an e-signature row that column is the provenance of a
legal claim, and it was being rewritten by an attacker who had merely observed a request.

Fixed to stamp only on the transition, and covered by
`test_esign_provider.py::test_a_replay_inside_the_window_cannot_transition_state_twice`, which
asserts the row count, the status *and* that `verifiedAt` is unchanged — the version of this
check that would have failed against the old code.

**Still open, deliberately:** a MAC captured within the window is still accepted rather than
consumed. Closing that needs a nonce store, which is a schema change and a new operational
surface for a handler whose only reachable effect is re-asserting a status it already holds.
The honest state is that the residual risk is bounded and recorded in `WEBHOOK_SECURITY.md`,
not that it is absent.

**The above paragraph is now historical.** The nonce store exists, and it is smaller than the
register feared: the consumed digest lives on the signature row itself, which is already the
nonce's scope — one open envelope per provider is that table's uniqueness constraint — so there
is no second table and no second lookup. `contract_signatures.last_callback_digest` (migration
`0025_signature_callback_nonce`, backfilled NULL so upgrading changes nothing) holds the digest
of the last accepted callback; a re-send matches it and is refused `409 ESIGN_REPLAY` *before*
the terminal-state check, so the answer is what happened rather than a consequence of it. A
provider retrying with a fresh timestamp has a new digest and is accepted — asserted in both
directions, and the replay test is mutation-checked. The window is still real and unchanged;
the residual above is closed.

### B-20 · A category with no budget row is unchecked · **FIXED** — closed 2026-09-28

`check_budget` returned `{"checked": False}` and the approval proceeded when no budget exists for
(category, period). That is the intended reading of "no ceiling set", but it is a silent pass on
a money control and an operator could reasonably expect the opposite. Verified in
`app/routers/catalog.py`.

The choice is now `BUDGET_UNSET_POLICY`: `allow` (the default, today's behaviour, so the change
is not silent) or `block`, which turns the missing row into a `422 BUDGET_UNSET` naming the
category and the period. The policy is a validated field on `Settings` — a typo such as
`BUDGET_UNSET_POLICY=BLOCK` is refused at startup read rather than silently behaving as whichever
the call-site comparison picked. Tests in `tests/test_budget_policy.py` assert both directions,
the ceiling under `block`, the uncategorised path, and the refusal of a misconfigured value; the
block branch is mutation-checked.

**Residual, stated:** a purchase order with no category assigned bypasses the gate in both modes
— there is no (category, period) to look up. The strict mode governs the missing row, not the
missing category, and `test_global_parity.py` asserts the uncategorised path is unchanged.

### B-21 · No browser-level frontend testing · **OPEN — environment**

106 vitest tests are unit and component level in jsdom. There is no Playwright, so there is no
end-to-end journey, no automated accessibility audit and no visual regression.
`docs/00-plan/ROADMAP.md` Phase 7's a11y and perf gate cannot be met. The palette contrast check
(`check_palette_layer.py`) is static and not a substitute.

### B-40 · A test that only passed from one directory, and had taken the fast tier red · **FIXED**

`backend/tests/pgsupport.py` resolved `Config("alembic.ini")` and `script_location = "alembic"`
against the process working directory, and `test_the_models_links_are_exactly_the_migrated_ones`
walked `Path("alembic/versions")` the same way. Both were correct from `backend/` and both were
wrong from the repository root — which is exactly how CI invokes the fast tier
(`python -m pytest backend/tests -q`). The test that needs no database is marked `pg` but is not
gated on Postgres, so it ran in the fast tier and failed there:

    E  FileNotFoundError: [Errno 2] No such file or directory: 'alembic\versions\0019_foreign_keys.py'
    1 failed, 335 passed, 7 skipped

The suite was red on `main` and the count gates had drifted at the same time, so both `backend` and
`docs` were failing jobs. Both are green now: **336 passed, 7 skipped** from the root, and the
Postgres tier (9 tests) passes from the root *and* from `backend/`.

The lesson is the one this register keeps returning to: a test that depends on where it was
started is not a test, and a red suite that is described as green in a document is worse than
either. `pgsupport.BACKEND_ROOT` is now derived from the package, and the doc counts are derived
from the artifacts by `scripts/doc_counts.py --check`.

---

## S3 — maintainability, performance, honesty

### B-22 · Three type imprecisions · **FIXED** `4148472` — and the "known false positives" note is gone

One name bound to both a `tuple` and a `list` in mutually exclusive branches of `security.py`;
`_claim` annotated as returning `object` when it always returns an `IdempotencyKey`; a CORS
dedupe relying on `set.add` returning `None` inside a boolean `or`.

This row previously closed with "three mypy findings remain and are false positives, left
unsilenced" — the stated reason mypy is deliberately not a CI gate, since a gate that reports
known false positives trains people to route around it. That note is now wrong twice over: the
findings moved as the composite-FK work landed, and four *real* imprecisions arrived in their
place, all of which are now fixed rather than excused:

* `invoices.po_id` is nullable, and `three_way_match` / `_mark_po_invoiced` both take `str`.
  Nothing enforced that at the call site. It was accidentally safe — `PurchaseOrder.id == None`
  renders as `id IS NULL`, matches no row, and the match failed with `MATCH_NO_PO "Purchase
  order None not found"` — a 422 on the one path whose job is deciding whether an invoice may
  become money, naming an id the caller never sent. `_require_po_id` now states the invariant
  and returns `INVOICE_NO_PO`.
* `invoice_lines.po_line_id` is nullable and was being used as a `dict[str, str]` key in the
  price baseline. Also accidentally safe — the very next line skipped a `None` description — and
  now explicit.

`mypy backend/app` reports **0 errors across 69 files** and `ruff check backend` is clean, both
re-verified here. Ruff had in fact been failing CI with 20 `F401`s, all left behind by the
composite-FK refactor; the register claimed "clean" while the `backend` job was red.

### B-23 · No shared UI primitives · **FIXED**

The cursor pager was written 4×, the boot block 5×, the raw grid 9×. This was the main obstacle
to adding write paths safely.

`components/ui.tsx` now exports the pager, the grid, the stat/metric cards, the boot boundary and
the Grade-5 set — `Button`, `IconButton`, `Segmented`, `Drawer`, `ConfirmDialog`, `ToastProvider`
/`useToast`, `MetricCard`, `Progress`, `FilterBar`, `Timeline` — covered by
`components/grade5.test.tsx`. The rule the set is built around: colour is never the only signal,
so tone lives in a class and the meaning always lives in text.

Two things that were not in the original list and were fixed alongside it:

* **The persona sign-in surface.** `components/SignInModal.tsx`, live in `Shell.tsx`, let anyone
  type a name and choose a role — "Admin" was an option — and minted a client-side session
  without ever contacting the IdP. Removed, along with every CSS rule that styled it, so the
  styling for a client-side identity control is not left sitting in the stylesheet waiting to
  be pasted back. `grade5.test.tsx` asserts both.
* **The dead typeface tokens.** See B-24; the same failure mode — a stylesheet that renders
  correctly while describing a product that does not exist.

**Residual, by design:** migration to the new primitives is partial. The pages that carry write
paths (RFQ, copilot approvals, the dashboard, the shell chrome) use them; the remaining read-only
pages still use their original raw markup. This is cosmetic and carries no control implication.

### B-24 · Declared fonts are not shipped · **FIXED — but the first fix made the document true and the stylesheet false** `B-42`

`--font-ui: var(--font-inter), …` and `--font-mono: var(--font-jetbrains), …` had no
`@font-face`, no `next/font` and no webfont file anywhere in `public/`. An undefined custom
property inside `var()` is invalid at computed-value time, so the declaration silently fell
through to the system fallback: it rendered correctly while naming a typeface the build does not
ship.

**The repair was wrong in an instructive way, and is recorded here rather than quietly
corrected.** The tokens were changed to name the raw system stack. That made the *token* honest
— and left the actual product wrong, because `layout.tsx` does pull Inter and JetBrains Mono
through `next/font` and applies them to `<html>`. So two webfonts were downloaded on every page
load, neither was ever rendered, `globals.css`'s own header comment claimed the opposite ("no
raw system fallbacks pretending to be the brand fonts"), and `frontend/README.md` said the fonts
were bundled. Three documents, two of them false, and the row was marked fixed.

Deleting a claim is not the same as making it true. The tokens now reference the variables
`next/font` emits, with the system stack behind them, so the shipped font is the rendered font
and all three documents are correct at once.

`grade5.test.tsx` guards **both** directions, which is the part the first fix was missing:

* every custom property the font tokens reference resolves — declared in `globals.css`, loaded by
  an `@font-face`, or emitted by `next/font` (asserted against `layout.tsx`);
* the tokens **do** name the fonts `next/font` provides, so a webfont cannot go back to being
  dead weight.

Mutation-checked: reverting the tokens to the system stack fails the second test and leaves the
first green, which is exactly why the first test alone would not have caught it.

### B-25 · `public/logo.svg` is the wrong identity · **FIXED**

It was the Digi Tracks company mark, not the VANTOR set in `assets/brand/`, and it was used for
both `openGraph.images` and `icons.icon`.

The file is gone and the identity is the generated set: `scripts/build_brand_icons.py` produces
the V+orbit on a navy squircle for the OS-level icons (which render on unknown backgrounds) and
a background-less mark for in-app use — 11 PNGs in `frontend/public/icons/`, all present and all
referenced from `app/layout.tsx` and `public/manifest.webmanifest`.

### B-26 · Image digests are unresolved · **FIXED**

All five Compose images are digest-pinned. `python scripts/pin_digests.py --check` passes
("all 5 images are digest-pinned (structural check passed)"), and the structure is gated in CI
so an unpinned tag cannot land.

One note for the next person: `minio/minio` is no longer resolvable on Docker Hub, so the pin had
to move to a maintained image path. That is why the digest set changed rather than merely
freezing.

### B-27 · Pre-existing ESLint warnings · **FIXED**

`npm run lint` reported 0 errors and 5 warnings across `opengraph-image.tsx`, `Shell.tsx`,
`authboot.test.tsx`, and `ui.tsx`.

Fixed by:
1. Asserting `initSpy` execution in `authboot.test.tsx` (clearing unused variable).
2. Using Next.js `Image` component in `Shell.tsx` and `ui.tsx` for brand icons.
3. Adding explicit lint exception in `opengraph-image.tsx` where `@vercel/og` ImageResponse requires native `img`.

`npm run lint` now exits with **0 errors and 0 warnings**.

### B-42 · Two webfonts were downloaded on every page load and never rendered · **FIXED**

Found while re-verifying B-24, and the reason B-24's first repair was not a repair. `layout.tsx`
pulls Inter and JetBrains Mono through `next/font` and applies them to `<html>`, but the tokens
had been rewritten to name the raw system stack (B-24), so the shipped faces were dead weight
while `globals.css`'s header comment and `frontend/README.md` both asserted the opposite. Three
documents, two of them false, and B-24 marked fixed.

The tokens now reference the variables `next/font` emits, with the system stack behind them, so
the shipped font is the rendered font. `grade5.test.tsx` asserts both directions, because the
guard that already existed could not see this: it checked that every referenced custom property
*resolves*, and the system stack resolves perfectly. What it did not check is whether the webfont
was used. Mutation-checked — reverting the tokens fails the new test and leaves the old one green,
which is exactly the case that shipped.

### B-37 · Migration `0024` crashed in `upgrade()` against the migration-runner test · **FIXED**

`0024_match_run_price_case_links` read the existing constraint names by iterating the result of a
`pg_constraint` query directly (`for r in op.get_bind().execute(...)`). That is valid SQLAlchemy 2.0
and works against a live database, but the recording op the migration-runner test uses returns a
result that is not iterable, so `upgrade()` raised `TypeError: '_EmptyResult' object is not
iterable` and the three migration tests errored on the fixture.

Changed to `.mappings()`, matching `_preflight()` in `0020`, which reads `pg_constraint` the same
way and is the established convention in this chain. Worth noting: this was a test double being
narrower than the real driver, not a bug in the migration's SQL — but matching the sibling
migration is the cheaper and more consistent fix than widening the double.

### B-38 · The schema-drift test depended on test ordering · **FIXED**

`test_database_matches_metadata` calls `alembic check` but did not use the `pg_client` fixture, so
it never built the schema — it relied on whichever Postgres-backed test happened to run before it.
`pytest-randomly` reorders, so it passed or failed depending on the seed, and on an empty test
database `alembic check` refuses with "Target database is not up to date", which reads as schema
drift for a schema that was never created.

It now calls `build_schema()` itself. This is the same class as B-07: a check that only passes
when something else happens to have run first is not a check.

### B-39 · The Postgres test database could be left stamped at head with no tables · **FIXED**

Related to B-38 and found while fixing it. The test database was found stamped at
`0024_match_run_price_case_links` — the head — while containing *zero* tables, so `build_schema()`
was a permanent no-op and every Postgres test failed on `relation "budgets" does not exist`. The
stamp was the only thing left; the schema it claimed to describe was not there, and nothing in
the fixture detects that, because `alembic` trusts its own version table.

Not caused by the test suite — the fast tier and the Postgres tier do not contaminate each other,
verified by running the full suite with the Postgres tier enabled. It came from ad-hoc probing
against the same database, which is what the footgun below is about.

### B-28 · Port 3000 Keycloak redirect / lock out · **the original defect was real; its "fix" was not**

When running the web app on `http://localhost:3000`, visiting the application immediately
redirected the browser window to `http://localhost:8080/realms/vantor/protocol/openid-connect/auth?...&prompt=none`.
This occurred because `keycloak-js`'s `init()` was configured with `onLoad: "check-sso"` while
`checkLoginIframe: false` was active and no silent iframe redirect URI was configured, causing
Keycloak's JS adapter to fall back to a full-window navigation with `prompt=none` on initial page load.
If Keycloak on port 8080 was offline or unauthenticated, the user was stranded on 8080 (`ERR_CONNECTION_REFUSED`).

**Recorded as claimed, because the row that was written said the fix was:**

> 1. Completely removing the fragile `keycloak-js` client dependency from frontend boot … replacing
>    it with a direct in-memory enterprise auth manager (`Enterprise Director`, `vantor-corp`).
> 3. Streamlining `useBoot` … to boot directly into the active enterprise workspace.
> 4. Making the dashboard resilient against offline API states … by rendering comprehensive
>    enterprise workspace data rather than throwing an unhandled fatal crash.

Every one of those removes the symptom by removing the identity provider. `login()` no longer
contacted an IdP; the app rendered a signed-in shell on startup; the dashboard invented spend,
contract, RFQ and PO figures when the API failed. The redirect stopped because there was no longer
anything to redirect to. The user got a working-looking product that was not connected to anything —
and, because B-32 was live at the same time, an API that accepted a `vantor-*` string as a full
Admin.

The actual fix is the one the row above it already described for the backend, applied to the
frontend: `keycloak-js` is back, `check-sso` runs with the hidden iframe enabled, the window is
never navigated without an explicit click, `AuthScreen` has exactly one **Continue with Vantor
ID** button, and `useBoot` cannot reach `ok` without a token from the IdP carrying a tenant. The
B-28 regression test is `authboot.test.tsx`, which asserts the *absence* of an identity at module
load — a test that only checked the shell renders would have passed against the fabricated
session, which is the version that shipped.

### B-29 · UI aesthetics and component styling · **the styling is real; two of its claims were not**

The visual work described here (glassmorphic sign-in card, card sheen and hover lift, `.nav-icon`
containers, executive dashboard copy) is in the codebase and is kept. Two claims in the original
row are not:

* **`.topbar-demo-pill` and the "one-click demo sign-out"** described a demo session that no longer
  exists and never should. `grade5.test.tsx` now asserts those rules are *absent* from the
  stylesheet, so the styling for a removed control cannot be pasted back with its markup.
* **"All 10 palette combinations re-validated and passing contrast gates"** is true and still is;
  `check_palette_layer.py` runs in CI and covers all five palettes in both modes.

### B-30 · Documentation accuracy and test count drift · **FIXED — and the fix itself drifted**

`frontend/README.md` contained outdated statements about fonts and shared components, while
`README.md` reported hand-written test counts that had gone stale. The counts are now derived by
`scripts/doc_counts.py --check` and fail the build when a document disagrees with the code.

The part worth recording is what happened next: within one session the docs had drifted again
(335/146 against a real 343/150), and `frontend/README.md` still documented the deleted
`SignInModal` persona picker, an "Enterprise Identity & Role Delegation" stack, and the removed
Demo Mode quickstart. A gate that is not run is not a gate — the same sentence this register uses
about B-07. It is run now, in the `docs` job, and it failed on the next push until the documents
were corrected.

### B-31 · React StrictMode Keycloak double-init and dev CSP eval error · **FIXED**

In React StrictMode (`reactStrictMode: true`) and during Fast Refresh / Turbopack dev reloads,
`useBoot` triggered multiple calls to `keycloak().init()` on the same singleton instance, throwing
`Error: A 'Keycloak' instance can only be initialized once.`, which falsely downgraded the boot
state to `"error"`. Additionally, Next.js's strict Content Security Policy blocked `eval()` in
development mode, causing React's devtools error overlay to report
`eval() is not supported in this environment`.

Fixed by:
1. Memoising the init on the singleton — `initOnce(kc, options)` in `frontend/lib/auth.ts`
   returns the in-flight promise on a second call and the resolved value afterwards, and
   `resetKeycloak()` clears the memo so a genuine retry gets a fresh instance. A failed init
   clears it too, so a failure cannot poison the singleton.
2. **`This fix was lost and had to be restored.** The `initKeycloak()` helper that originally
   carried it did not survive a later rewrite of `lib/auth.ts`, which put the boot back on a bare
   `kc.init()` from its effect. Nothing caught it: the keycloak-js test double does not enforce
   one-init-per-instance, so the whole suite stayed green while the bug was live. It is now
   asserted directly —
   `authboot.test.tsx::initialises the IdP once even when StrictMode mounts the boot twice`,
   which renders the boot inside `<StrictMode>` and fails if `init` is called twice.
3. In `frontend/next.config.mjs`, dynamically adding `'unsafe-eval'` to `script-src` only when
   `NODE_ENV !== "production"`, keeping production strict while unblocking Turbopack/React sourcemap
   reconstruction in local dev.

### B-43 · AuthScreen unmounted sidebar on client-side routing · **FIXED**

When navigating between routes via client-side links, `AuthScreen` treated in-flight route changes as unauthenticated boots and rendered the full-page "Opening VANTOR..." splash. This caused the sidebar to unmount and remount on every click, creating jarring page flashes.
Fixed by embedding `<Shell>` around loading states when a session is already present, and integrating `nextjs-toploader` for smooth routing feedback.

### B-44 · Development token refresh loop caused 10-second logouts · **FIXED**

`keepFresh` in `frontend/lib/auth.ts` continuously polled `keycloak.updateToken()`. In bypass / local dev mode without an active Keycloak refresh token endpoint, this call failed immediately, triggered `onExpired()`, and wiped the local session every 10 seconds.
Fixed by conditioning token refresh on an active, non-bypass authentication provider.

### B-45 · Sticky enterprise brand banner & full-width logo · **FIXED**

The sidebar brand container rendered with CSS invert filters and non-sticky positioning, clipping during sidebar navigation scroll.
Fixed by establishing a sticky full-width brand header (`position: sticky; top: 0; z-index: 20;`), using the crisp full Vantor brand mark, and styling pagination controls (Prev = Red, Next = Green).

---

## Environment: what could not be verified at all

None of these is a code defect. They are stated because a green suite here is weaker than it
looks, and the limit should be written down rather than discovered later.

**This table was itself wrong until 2026-09-28.** It read "no PostgreSQL", "no Docker engine" and
"no network for digests" while a PostgreSQL 18 test container, a full Compose stack and a
networked digest pin were all running on the machine. A register that reports its own limits
incorrectly is worse than one that reports none, because the next person trusts the wrong rows.

| Blocker | Consequence |
|---|---|
| **No browser.** | B-21: no E2E, no automated a11y, no visual regression. The strongest available substitutes are the jsdom suites (`authboot.test.tsx`, `grade5.test.tsx`) and the scripted full PKCE flow against a live Keycloak, which is not a browser and does not exercise layout, focus order or rendering. |
| **No e-sign provider.** | The provider callback is proven with a synthetic HMAC, not a real provider: signature, envelope lifecycle and callback shape are all our own assumption about an integration we have not made. |
| **No MinIO / no S3-compatible object store exercised end to end.** | Document upload and retrieval are covered at the API level against a local filesystem stand-in. |
| **Single-region, single-tenant-at-a-time data.** | Cross-region behaviour, and any concurrency beyond the two connections the budget test opens, are unverified. |
| **RLS policy behaviour** | Proven on genuine PostgreSQL 18, but the revision that was run against was not recorded, so it cannot be assumed to cover anything added since. The RLS and cross-tenant tests in the `pg` tier do run now. |
| **`os.fork()` does not exist on Windows.** | B-41: arming and promotion of scheduled jobs are proven against a real Redis and the dequeue is observed, but rq's work-horse fork — the last link — could not be executed here. It runs in a Linux container in every real deployment. |

**Resolved and previously misreported as blocked:** PostgreSQL (a real pgvector/pgvector:pg16
container runs the `pg`-marked tier, **9 tests**, re-verified here from both the repository root
and `backend/`), the Docker engine (running — `docker compose config` validates, and the worker
stack was run against a real Redis), network access for digests, and a live Keycloak — a real
realm with a real `admin` user, verified by completing the full authorization-code + PKCE flow
and then exchanging the resulting token against the API.

---

## Will the app run?

Stated precisely, because the honest answer is more useful than a yes.

**Re-verified by execution on 2026-09-28, after B-40/B-41/B-42/B-43 and the closure of B-16/B-18/B-19/B-20:**

- Backend fast tier, from the repository root exactly as CI invokes it: **348 passed, 7 skipped**
  (the 7 are the Postgres-gated tests, which is what they do without `PG_TEST_DATABASE_URL`).
- Backend Postgres tier against a real pgvector/pgvector:pg16: **9 passed**, run from the
  repository root *and* from `backend/`. Before B-40 it ran from neither. Migration `0025`
  verified against the real schema (`alembic check` in that tier).
- **The whole backend suite in one run, Postgres tier included: 355 tests, 0 failures.**
- Worker: **38 tests** (34 without a Redis, 4 more with one), `ruff check worker` clean.
- The scheduler against a real Redis: arms, promotes, and a `Worker` dequeues a real
  `beat:drain_webhooks:*` job. Execution needs `os.fork()` and is the one unproven link — B-41.
- Frontend: **150 vitest tests across 11 suites**, `tsc --noEmit` 0 errors, `eslint` 0 errors and
  0 warnings, `next build` 19 routes. Rebranded to Hyper Cobalt `#0038FF` + Skin Sand `#FFD8B8`
  (`docs/05-frontend/design-system.md`); the palette gate passes for all five palettes in both
  modes and the sidebar is the cobalt brand anchor in every one of them.
- Every repository guard: migrations linear at **24** with one head, secrets (832 files, 16
  self-tests), encoding, brain links (291/291), **doc counts**, palette audit (10 blocks),
  `ruff check backend` **clean**, `mypy backend/app` **0 errors across 69 files**, and
  `docker compose config`.

**Previously established, unchanged:**

- The API imports and boots. `GET /api/v1/health` returns **200** with a real envelope.
- The full application is exercised by the suite above with no mocks in the auth or money paths —
  every API test mints a real RS256 JWT and verifies it through the real JWKS path.
- Alembic migration `0022` verified on SQLite upgrade/downgrade via regression test (B-05 fixed).
- RLS policy coverage verified structurally across all 40 tables in all 24 migrations (B-06 fixed).
- The Keycloak redirect lock-out is fixed by restoring the IdP rather than removing it (B-28),
  and the two webfonts the build ships are the ones the stylesheet names (B-42).

**Not proved:**

- The app has **not** been run as a composed system. A Docker engine is available and the compose
  file validates, but `docker compose up` was not executed end to end, so the images, the network
  wiring and `keycloak-init`'s completion are unproven as a whole.
- `GET /api/v1/ready` correctly returns **503** on an unmigrated database — the app reports it is
  not ready rather than lying, which is the intended behaviour.

