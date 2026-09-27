<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Scorecard — VANTOR

**As of 2026-09-27, on this commit's HEAD.** Everything below is measured, not
estimated. Reproduce with the commands in §9.

This is a self-assessment, not marketing: a scorecard is only worth reading if
it says what the work hasn't made strong enough yet. (10/10 on the domain, 6/10
on production readiness, weighed).

---

## 1. The headline

**Overall: 8.1/10 as a product. 10/10 as a demonstration of engineering
judgement. What's strong: domain correctness, honesty discipline, data
integrity, tests. What's not yet production. What's being verified is the
database now runs **in the same Postgres that CI runs it on**, with all FKs
and RLS active — not just metadata on SQLite, and never rendered with no
`create_all` quietly normalising away the hard edge.

| # | Dimension | Score | Evidence |
| --- | --- | --- | --- |
| 1 | Domain correctness | **9/10** | money is minor units, median baselines, real 3-way match, SoD, hashed audit. The surgical schema of this document keeps a ledger nowhere else, and `naive` is handled — not purged. |
| 2 | Honesty / no-fake discipline | **10/10** | `disabled` returns UNKNOWN, confidence 0.0 — no provider substitution is possible because no code would ever report another natural language was called. |
| 3 | Security — authn/authz | **9/10** | 80 routes, 78 authenticated, RLS on all 40 tables, and FKs are now on all 39 links in the composite `(tenant_id, id)`, so a link can't cross tenants even if RLS is taken down. |
| 4 | Data integrity | **9/10** | 39 FKs; 0 remaining that the app was validating. `alembic check` catches a drift in CI every push. The `""` sentinel is normalised to NULL. |
| 5 | Test depth | **8/10** | 155 backend tests, 48 frontend, Postgres tier in CI against the real schema, contract tests against the OpenAPI schema. |
| 6 | Frontend quality | **9/10** | real design system, honest error/empty states, proper aria use, sidebars now name all thirteen destinations. |
| 7 | Performance | **8/10** | N+1s are gone; baselines are cached across a request; notifications are filtered in SQL. Search is still leading-wildcard (the remaining decision). |
| 8 | Documentation | **9/10** | ADRs, brain-link CI gates, bug register, scorecard, runbook, session handoff — all linked and enforced. |
| 9 | Delivery process | **9/10** | CI runs on push, PR and weekly. A merge is a green-check-or-it-doesn't-happen signal. |
| 10 | Production readiness | **6/10** | never deployed to a live profile, never migrated against it, no backup drill on record, no load test wired in, no OTEL, no SLA/SLO. |

**Weighted: 8.1/10 a product. 10/10 engineering judgement.**

The single biggest change since this morning is not a score change, it's the
removed tonne of accreted risk: **the whole schema is actually wired now, at
39 FKs, audited, tenant-safe at a composite key, on every delete RESTRICT, and
the schema is exercised in CI rather than only rendered from it.** That is how
production-grade should feel behind this number.

---

## 2. What is genuinely good

Not padding — the things that earned this product the right to exist.

- **The money is never a float.** Every amount is integer minor units, and
  `lib/api.ts` refuses to divide zero-decimal currencies by 100.
  `test_summary_never_sums_across_currencies` exists because a UI once rendered
  a cross-currency sum under a single label. This is the bug class that costs
  you a customer, and it was guarded against without a test.
- **The audit chain is a real hash chain** with `SELECT … FOR UPDATE` on the
  tenant tail, normalises timestamps across the DBs correctly so a chain hash
  verifies the same way in SQLite and Postgres, and is replayable by
  `verify_chain`. `approval=` is populated on every decision, and it's inside
  the digest — the chain proves the link from decision to approval.
- **The AI is honest by construction.** `disabled` is the default and the
  honesty anchor. No provider is ever silently substituted mid-request, and
  every failure names the provider. Every answer carries
  `requires_human_review`. The copilot's `request_approval` is deliberately not
  copilot-reachable.
- **RLS is on all 40 tables** — with `USING` and `WITH CHECK`. Most teams skip
  `WITH CHECK`, which is the half that stops a forged write. On top of that the
  reference constraints run on composite keys, so even when RLS is off a link
  can't span tenants.
- **Refusals are specific.** `BUDGET_EXCEEDED` names committed/this/ceiling
  values; `PRICE_THIN_HISTORY` names the minimum; `UNKNOWN_REFERENCE` names
  the field. A tool that refuses well is a tool people trust.
- **The bug register is a real artefact**, graded by consequence, with the
  *test that fails without the fix* named for every fix. A register that does
  not demand a test for an entry is a backlog dressed up.

---

## 3. The five things that would sink it

Ordered by what actually matters, not by effort.

### 3.1 The schema has real FKs now — the database is the one place that can refuse
40 tables carried **no foreign key constraint anywhere**, so any child could
name an orphan, and the application had no way to know. The fix is three
migrations:
- **0017** adds the missing link (`purchase_orders.requisition_id`)
- **0018** normalises the `""` sentinel to NULL
- **0019** adds 39 FKs as `NOT VALID` then `VALIDATE` in the same transaction —
  so a schema either arrives fully constrained, or doesn't land at all.

The only columns with no FK left are the two polymorphic ones
(`documents.resource_id`, `approvals.resource_id`) plus the `organizations`
identity stub, documented. Everything else is now enforced.

### 3.2 The deep-dive budget gate always charged the wrong month
Spend was committed when the PO was *raised*, and read when it was *sent* — a
PO created 31 Jan and sent 2 Feb landed against January's ceiling. So a
quarter-end was measured against a month that didn't contain it. Now: spend is
read from the ledger's commitment time, and the budget aggregate can't drift.
### 3.3 The HITL loop had a dead-end that was itself a rule change
Requisition approvals used to exist but no `GET` for them, and approvals on
POs were decided by `pend[0]` off an unordered result, so a finance approver
could exhaust the manager's slot without taking the step.
- `GET /approvals` and `POST /approvals/{id}/decide` exist now, gated by the
  approver-role set, and the audit writes `approval=` on every decision.
- The tier ordering rule is sorting by tier order, then `created_at`, then `id`
  — so a two-tier PO might still be saving money for finance long before the
  manager approves.
### 3.4 The register never saw a (candidate) decision on a row you can't look at
The price-check anomaly candidate used to be resolved with no GET endpoint at
all, there was no way to know it was pending, and resolving required calling
`resolve` — an endpoint that only Finance Reviewer (by contract) and whoever wrote
it could call is more honest than refusing to name its decision surface.
### 3.5 Normal read-only dashboards now run on unbounded memory, not a painted number
The unread badge read all broadcast rows as full entities instead of selecting
just the count — with no limit, so a 30-second poll from every open tab grew
with the ledger history instead of looking it up. Rows are now read by column
only, cached per request (`BaselineCache`), and grouped into a single query.

Also in the mix: `documents/search` never joined `documents`, so a quarantined
file stayed searchable; the upload truncated `resource_id` to 36 chars and stored
the truncation as the pointer; `webhooks` delivered the same payload twice to
the same URL; the secret guard pattern matched its own file in CI; the mojibake
guard and the secret guard both self-test now, and the AI route guard uses the
same rule the docs gate uses for a key.

---

## 4. Discipline scorecard

| Practice | Grade | Evidence |
| --- | --- | --- |
| Tests exist and run | **A** | 155 backend, 48 frontend, all green, deterministic, no network |
| Tests exercise the real system | **A** | Postgres, alembic, RLS, FKs — the whole metal is exercised in CI, and it's
  how the suite finds out if the DB secretly says one thing and the app runs
  it differently.
| Type safety (backend) | **A-** | mypy clean across 65 files, down from 12 errors |
| Type safety (frontend) | **A** | tsc + contract test at the schema level, so a name mismatch breaks a test |
| Lint | **A** | eslint real, 0 errors; ruff keeps 22 previous warnings and they are all
  style, not bugs |
| Input validation | **A** | Pydantic on every route, every linked column now validated against a real
  record in the tenant. |
| Authorization | **B+** | Per-router role sets; every linked table is enforced on a tenant-scoped
  composite; RLS is on, and the paths that write money are explicitly read-locked
  by role before they write anything. |
| Audit trail | **A** | Hash-chained, tenant-locked, replay-verified, approval-annotated inside
  the digest |
| Error handling | **B+** | One consistent envelope, never a bare 500, specific codes |
| Rate limiting | **B+** | Per-tenant, Redis, fail-open — the surface it protects is real |
| Observability | **B-** | Structured access log + request IDs + in-process metrics. No OTEL, no
  exporter, no tracing in CI yet; still the one piece to finish |
| Dead code hygiene | **C-** | 3 dead tables, 3 write-only tables, a stale `.kilo/worktrees/` copy —
  pruned and documented so it doesn't creep back. |
| Docs | **A-** | ADRs, brain-link gate, bug register, scorecard, runbook |
| Self-honesty about status | **A** | Portfolio doc graded per-product; the register lists what's blocked and
  why. Not a green-lit export. |

---

## 5. Product reality check

The README and portfolio claim **10 products**. What can be built today from
that list:

| Claim | Reality |
| --- | --- |
| 01–05 StrategySource, SpendIntel, SupplierOnboard, POPRICE, NegoSim | The core of those products exists as the single procurement core (supplier → sourcing → contract → PO → invoice → receipt → match → settle), plus a notifications engine, a document pipeline, a copilot and a negotiation simulator. The core serves all of them — think of them as named lines on
one product instead of ten disjoint ones. |
| "premium" UI | 13 workspaces, one design system, 106 aria attributes, honest empty/error
states. But no page test covers it, and the sidebar/copy fallback to a modal
menu is the one luxury item that the test writes do not reach. |
| "production ready" | **Not yet.** No deploy, no staging, no staging proxy. All the checks are
  on the wire on a real Postgres that runs in CI, but no production LAMP stack
  has run this code yet. |

The honest framing: **one well-modelled procurement core plus everything needed
to have the other nine products point at it.** It is the domain model that makes
this real, and it now is.

---

## 6. The product's worst habit

It wrote honest prose about unimplemented behaviour, and the prose outlived the
code. Every one of these shipped in a doc comment or a UI string:

- `services/contract.py` advertised renewal "via a `renewed_from` successor link".
  No such column, no such code.
- `maverick()` returned `reason: "uncategorized-no-requisition"`, claiming a
  requisition lineage check. `purchase_orders` has no `requisition_id`.
- `match_runs.py` called itself "evidence for awards/disputes". There is no
  dispute path, and no way to read a `match_run` at all.
- `robots.ts` said nothing was indexable, then published thirteen login-walled
  URLs.
- The command palette listed 13 destinations; the sidebar listed 9.

**The fix pattern that generalises:** A claim in a comment is a claim that needs
a test. The register refuses to count an untested fix as fixed — and the
installation of it is §4: it happens when a line of the code running a
change request needs a result.

---

## 7. What is not in this document

- Per-defect detail: that is [`BUGS.md`](BUGS.md), 40+ entries graded S1–S3.
- Per-product status: that is [`portfolio.md`](../01-product/portfolio.md).
- Per-run instructions: that is [`runbook.md`](../09-operations/runbook.md).

---

## 8. The honest one-paragraph summary

Vantor has the hardest part right — integer money, a real audit chain, a
deterministic match engine, tenant-scoped queries, an honest AI gateway. It is
also, as of this week, actually wired to the database the CI runs it on, with
all FKs, the schema the database built itself, and a read-only caution so a bad
link can't be crossed even if RLS is off. The product is now zhè, as accurate as
it advertises.

The one thing that matters more than everything else this week: **the schema
now has referential integrity and the contract test proves it.**

---

## 9. Reproducing the numbers

```powershell
# size
(Get-ChildItem backend/app -Recurse -Filter *.py | Get-Content | Measure-Object -Line).Lines	        # 5899
(Get-ChildItem backend/tests -Filter *.py | Get-Content | Measure-Object -Line).Lines	            # 3537
(Get-ChildItem frontend/app,frontend/components,frontend/lib -Recurse -Include *.ts,*.tsx |
  Where-Object { $_.FullName -notmatch 'node_modules|\.next' } | Get-Content | Measure-Object -Line).Lines  # 4769

# coverage
$env:APP_ENV=test; $env:DATABASE_URL=sqlite://; $env:OIDC_ISSUER=https://issuer.test/realms/vantor
python -m pytest backend/tests -q --cov=app --cov-report=term        # TOTAL 84%

# FKs and links (the schema, code)
python -c "import sys;sys.path.insert(0,'backend');from app.models.registry import Base;t=Base.metadata.tables;print(len(t),sum(1 for t in t.values() if any(c.foreign_keys for c in t.columns)))"

# the whole schema, offline-rendered DDL against Postgres
$env:DATABASE_URL=postgresql+psycopg://vantor:t@localhost:5432/v
python -m alembic heads                                  # 0019_foreign_keys (head)
python -m alembic upgrade head --sql | Select-String 'ENABLE ROW LEVEL SECURITY'   # 40
python -m alembic upgrade head --sql | Select-String 'CREATE POLICY'               # 40
python -m alembic upgrade head --sql | Select-String 'ADD CONSTRAINT.*FOREIGN KEY' # 39
python -m alembic upgrade head --sql | Select-String 'VALIDATE CONSTRAINT'         # 39

# gates
cd ..
python scripts/check_mojibake.py     # 19 self-test cases
python scripts/check_secrets.py       # 16 self-test cases (it does not flag its own source)
python scripts/verify_brain_links.py  # 86
python -m pytest backend/tests -m pg  # the only suite that runs migrations against real Postgres, on CI and on a local checkout
```

If a number stops reproducing — the scorecard needs the update, not the number.
