<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Scorecard — VANTOR

**As of 2026-09-27, commit `418346d`.** Every number below is measured, not
estimated. Reproduce with the commands in §9.

This is deliberately unflattering. A scorecard that flatters is a marketing
document, and the only useful thing about a self-assessment is that it names the
places where the work is not yet good enough.

---

## 1. The headline

**Overall: a strong prototype with a real domain model, and a product that is not
production-ready. It is not a demo — the money logic is real and the honesty
posture is genuine — but it has never run against real Postgres, has never been
loaded by a real user, and its most important safety property is untested.**

The single most damning fact is not a bug. It is this: **every test in the
repository runs against SQLite with `create_all`, never against the migrations
and never against Postgres.** RLS — the tenant-isolation mechanism the entire
security story rests on — has therefore *never executed once* in any test. A
class of defect that hid the idempotency overflow for the life of the project
would still hide the next one.

| # | Dimension | Score | One-line verdict |
| --- | --- | --- | --- |
| 1 | Domain correctness | **8/10** | Integer money, no floats, median baselines, real 3-way match, SoD, hashed audit chain. The strongest dimension. |
| 2 | Honesty / no-fake discipline | **9/10** | `disabled` mode returns UNKNOWN at confidence 0. Every skipped row carries a reason. The AI gateway has never claimed an answer it did not produce. Genuinely rare. |
| 3 | Security — authn/authz | **6/10** | 80 routes, 78 authenticated, RLS on all 40 tables, per-router role sets. But zero FKs, hard-coded role strings, and RLS unexercised. |
| 4 | Data integrity | **4/10** | **Zero foreign keys, zero `relationship()`.** Nine id columns now app-validated; the rest is convention. |
| 5 | Test depth | **5/10** | 84% line coverage on the backend is respectable; 11% src:tests on the frontend and a SQLite-only harness are not. |
| 6 | Frontend quality | **6/10** | Real design system, honest empty/error states, 106 aria attributes. Zero page-component tests. |
| 7 | Performance | **6/10** | Fixed the worst N+1s and full-table loads, but every search is leading-wildcard `ILIKE` on unindexed text. |
| 8 | Documentation | **8/10** | ADRs, brain-link CI gate, a live bug register, a runbook. Some of it was stale or self-contradicting until this week. |
| 9 | Delivery process | **3/10** | **CI runs weekly and nothing gates a merge.** That is the worst number on this page. |
| 10 | Production readiness | **2/10** | Never deployed. Never migrated on a live database. No OTEL, no backup drill on record, no load test in CI. |

**Weighted: 4.6/10 as a product. 8/10 as a demonstration of engineering judgement.**

---

## 2. What is genuinely good

Not padding — these are the reasons the project is worth continuing rather than
rewriting.

- **The money is never a float.** Every amount is integer minor units, and
  `lib/api.ts` refuses to divide zero-decimal currencies by 100. The test
  `test_summary_never_sums_across_currencies` exists because a UI once rendered a
  cross-currency sum under a single label. This is the bug class that destroys
  trust in a procurement tool, and it is handled.
- **The audit chain is a real hash chain** with `SELECT … FOR UPDATE` on the
  tenant tail, a normalisation that makes hashes reproduce across SQLite and
  Postgres, and a `verify_chain` endpoint. `approval=` is now populated, so the
  chain records *which approval authorised a change* and that field is inside the
  digest.
- **The AI is honest by construction.** `disabled` is the default and the
  honesty anchor. No provider is ever silently substituted mid-request. Failures
  name the provider. Every completion carries `requires_human_review`. The copilot
  is read-only by construction — `request_approval` is deliberately unreachable
  from it.
- **RLS is on every table** — 40 of 40, verified against the rendered DDL, with
  `USING` and `WITH CHECK`. Most teams skip `WITH CHECK`, which is the half that
  stops a forged write.
- **Refusals are specific.** `BUDGET_EXCEEDED` names committed/this/ceiling;
  `PRICE_THIN_HISTORY` names the count it needed; `UNKNOWN_REFERENCE` names the
  field. This is the difference between a tool people trust and one they route
  around.
- **The bug register is a real artefact**, graded by consequence with the
  regression test named for each fix, including the things that are *blocked* and
  why.

---

## 3. The five things that would sink it

Ordered by what actually matters, not by effort.

### 3.1 RLS has never run. At all. Ever.
40 tables have RLS policies. **Zero tests execute them**, because the harness
builds the schema with `create_all` on SQLite, which has no row-level security.
Every "tenant isolation" assertion in the suite is asserting that a `where
tenant_id == actor.tenant_id` clause is present in Python — not that the database
would refuse a write that forgot it.

This is not hypothetical. `idempotency_keys` had a production-only failure
hidden by exactly this blind spot. If a single write path anywhere forgets a
tenant predicate, Postgres is the *only* thing that would have caught it, and
Postgres is the only thing not being tested.

**Fix:** a Postgres-backed test tier, a subset of the suite run under real
`alembic upgrade head`, with at least one test per table asserting that a
cross-tenant `INSERT` is rejected by the database and not just by the
application. Estimate: one day. Value: it converts the entire security claim from
asserted to demonstrated.

### 3.2 Zero foreign keys across 40 tables
No `FOREIGN KEY`, no `relationship()`. Every link is a bare `*_id` string. Nine
columns were being written with no validation at all until this week. The routers
now validate the parents they can see, but nothing stops a direct SQL session, an
admin tool, a future migration, or the *worker process* from creating an orphan.

`supplier_certifications.document_id` was the sharpest example: a certification
claiming evidence from a document nobody can open, against a qualification gate
that counts verified certs. App-level validation is genuinely better than nothing
and genuinely not the same thing as a constraint.

**Fix:** an additive migration adding `NOT VALID` constraints for the pairs the
app already enforces, then `VALIDATE CONSTRAINT` after a cleanup query. Safe,
staged, and needs a decision.

### 3.3 Nothing gates a merge
CI is `schedule: weekly` plus `workflow_dispatch`. No `push`, no `pull_request`.
The `policy` job actively **fails** if triggered by push or PR. So the entire gate
set — 141 tests, the Alembic chain, the OpenAPI drift check, `pip-audit`,
`npm audit`, the brain-link check, the mojibake guard, the secret guard — is
advisory. It runs four times a month, on whatever is on `main`, and nothing is
blocked.

The evidence that this costs real money: the OpenAPI contract was stale and the
drift gate would have caught it — the gate simply never ran. The secret guard had
been failing on every execution for its entire life, because it matched its own
regex. Nobody saw either, because nobody was looking.

**Fix:** add `pull_request` to the `on:` block and delete the `policy` job's
fails-on-PR logic. Cost: CI minutes. The owner set a weekly budget for a
*different* set of repos; this one has 141 tests and should not share it.

### 3.4 The frontend has essentially no tests
`frontend/src` is 4,329 lines. `frontend/tests` is 466. The ratio is **1:0.11** —
one line of test per eleven lines of source. Four test files, two of which test
`components/ui.tsx`. **No page component has a test.**

Every frontend defect fixed this week was a response/contract mismatch that
`tsc` structurally cannot see, because `api<T>()` is an unchecked generic cast:

- `/ai/providers` returned `list[str]`, the UI typed `{name, configured}[]` →
  every provider rendered `undefined (not configured)`
- the optimizer's share-cap **violations** were discarded → a policy breach was
  invisible on a page promising capped splits
- price-evaluate reported "no history" for every skip, whatever the real reason
- `robots.ts` contradicted its own docstring

Not one would have been caught by a type check. All four were found by reading.

**Fix:** contract tests that assert a fixture response type-checks against the
generated OpenAPI schema. That single mechanism kills the entire class.

### 3.5 It has never run against Postgres
No live migration has ever been applied. The DDL is only verified by offline
render. `docker compose` has never brought the stack up on this machine. There
is no staging environment, no seeded demo tenant, no evidence the images build.

Migration 0016 is the first change to touch a column, and it has never been
executed by Postgres — only rendered. `alembic check` in CI has therefore never
run either.

---

## 4. Discipline scorecard

| Practice | Grade | Evidence |
| --- | --- | --- |
| Tests exist and run | **B+** | 141 backend, 48 frontend, all green, deterministic, no network |
| Tests exercise the real system | **D** | SQLite only; no Alembic, no RLS, no Postgres |
| Type safety (backend) | **A-** | mypy clean across 65 files, down from 12 errors |
| Type safety (frontend) | **C** | `tsc` clean, but `api<T>()` is unchecked at runtime |
| Lint | **B-** | ESLint real, 0 errors; ruff has 22 pre-existing `E741` and is not in CI |
| Input validation | **B** | Pydantic on every route; the nine unvalidated id columns now checked |
| Authorization | **C+** | Per-router role sets and 78/80 authenticated, but hard-coded strings and no FK-backed identity |
| Audit trail | **A-** | Hash-chained, tenant-locked, replay-verified, `approval` now populated |
| Error handling | **B** | One consistent envelope, never a bare 500, specific codes |
| Rate limiting | **B-** | Per-tenant, Redis, fail-open; 53% covered |
| Observability | **C** | Structured access log + request IDs + in-process metrics. No OTEL, no exporter, no tracing |
| Dead code hygiene | **D** | 3 dead tables, 3 write-only tables, a stale `.kilo/worktrees/` copy, an unused `pgvector` extension |
| Docs | **A-** | ADRs, brain-link gate, bug register, runbook |
| Honesty about status | **A** | Portfolio doc graded per-product; the register lists what is blocked and why |

---

## 5. Product reality check

The README and portfolio claim **10 products**. Brutally:

| Claim | Reality |
| --- | --- |
| 01–05 StrategySource, SpendIntel, SupplierOnboard, POPRICE, NegoSim | **Not built as products.** What exists is one procurement core (supplier → sourcing → contract → PO → invoice) plus a notifications engine, a document pipeline, a copilot and a negotiation simulator. 05 NegoSim is a deterministic rehearsal endpoint, not a simulator with scenarios. |
| "premium" UI | 13 workspaces, one real design system, 106 aria attributes, honest empty states. Genuinely above average for an internal tool. But no page test, and the 6 `next/image` warnings are unfixed. |
| "production ready" | **No.** Never deployed, never migrated live, no staging, no backup drill on record, no load test in CI. |
| Production Readiness doc | `docs/00-plan/PRODUCTION_READINESS.md` exists and has never been contradicted by a test. |

The honest framing: **this is one well-modelled procurement core with a copilot,
plus scaffolding that could host nine more products.** The domain model is
reusable; the nine products do not exist.

---

## 6. The product's worst habit

It writes honest prose about unimplemented behaviour, and the prose outlives the
code. Every one of these shipped in a doc comment or a UI string:

- `services/contract.py` advertised renewal "via a `renewed_from` successor link".
  No such column, no such code.
- `maverick()` returned `reason: "uncategorized-no-requisition"`, claiming a
  requisition lineage check. `purchase_orders` has no `requisition_id`.
- `match_runs.py` called itself "evidence for awards/disputes". There is no
  dispute path, and no way to read a `match_run` at all.
- `robots.ts` said nothing was indexable, then published thirteen login-walled URLs.
- The command palette listed 13 destinations; the sidebar listed 9.

Each is a small lie, and each one costs a reader more than the missing feature
would have. The fix that generalises: **a claim in a comment is a claim that needs
a test**, which is why the bug register now demands the regression test for every
entry and refuses to count an untested fix as fixed.

---

## 7. What is not in this document

- Per-defect detail: that is [`BUGS.md`](BUGS.md), 40+ entries graded S1–S3.
- Per-product status: that is [`portfolio.md`](../01-product/portfolio.md).
- Per-run instructions: that is [`runbook.md`](../09-operations/runbook.md).

---

## 8. The honest one-paragraph summary

Vantor has the hardest part right — integer money, a real audit chain, a
deterministic match engine, tenant-scoped queries, and an AI gateway that would
rather say UNKNOWN than lie. The engineering judgement is well above average and
the self-honesty is real. It is also, right now, a system that has never run
against its own database, never been loaded, and never had a merge blocked. The
gap between "the code is good" and "the product is trustworthy" is not closed by
writing more code; it is closed by three unglamorous pieces of work: a
Postgres-backed test tier, `NOT VALID` foreign keys, and a `pull_request` trigger
on CI. Those are days, not weeks, and nothing else on the roadmap matters until
they are done.

---

## 9. Reproducing the numbers

```powershell
# size
(Get-ChildItem backend/app -Recurse -Filter *.py | Get-Content | Measure-Object -Line).Lines        # 5899
(Get-ChildItem backend/tests -Filter *.py | Get-Content | Measure-Object -Line).Lines              # 3229
(Get-ChildItem frontend/app,frontend/components,frontend/lib -Recurse -Include *.ts,*.tsx |
  Where-Object { $_.FullName -notmatch 'node_modules|\.next' } | Get-Content | Measure-Object -Line).Lines  # 4329

# coverage
$env:APP_ENV=test; $env:DATABASE_URL=sqlite://; $env:OIDC_ISSUER=https://issuer.test/realms/vantor
python -m pytest backend/tests -q --cov=app --cov-report=term        # TOTAL 84%

# schema: FKs and relationships
python -c "import sys;sys.path.insert(0,'backend');from app.models.registry import Base;t=Base.metadata.tables;print(len(t),sum(len(x.foreign_key_constraints) for x in t.values()))"   # 40 0

# RLS and DDL, offline against the Postgres dialect
cd backend
$env:DATABASE_URL=postgresql://v:t@localhost:5432/v
python -m alembic heads                                       # 0016_idempotency_key_width (head)
python -m alembic upgrade head --sql | Select-String 'ENABLE ROW LEVEL SECURITY'   # 40
python -m alembic upgrade head --sql | Select-String 'CREATE POLICY'              # 40
python -m alembic upgrade head --sql | Select-String 'FOREIGN KEY'                # 0

# gates
cd ..
python scripts/check_mojibake.py     # 19 self-test cases
python scripts/check_secrets.py       # 16 self-test cases
python scripts/verify_brain_links.py  # 85
```

Any number on this page that stops reproducing is a defect in the scorecard.
Update the scorecard, not the number.
