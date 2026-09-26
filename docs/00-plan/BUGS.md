<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Bug & Risk Register — VANTOR

**Last updated: 2026-09-27. This is the single live register of known defects,
risks and deliberate omissions across the whole product.**

How to read the status column:

| Status | Meaning |
| --- | --- |
| `FIXED` | Repaired, with a regression test that fails without the fix |
| `FIXED (untested)` | Repaired, regression not yet pinned by a test |
| `OPEN` | Known, unfixed, not yet scheduled |
| `BLOCKED` | Cannot be fixed safely without a decision or a data pass |
| `BY DESIGN` | Deliberate, documented, do not "fix" |
| `DEBT` | Works correctly but is a structural liability |

Severity is about consequence, not effort: **S1** corrupts money, leaks a tenant
or silently disables a control. **S2** produces a wrong answer or strands a
user. **S3** degrades performance, ergonomics or clarity.

---

## 0. Ledger — what changed, and where

| Date | Commit | Theme | Tests |
| --- | --- | --- | --- |
| 2026-09-27 | `e3362af` | AI gateway key resolution, approval queue, idempotency width, referential validation, mojibake | 132 |
| 2026-09-27 | this commit | match engine false positives, award savings, notification paging, webhook fanout, optimizer explainability, guard self-test | 141 |

---

## 1. S1 — money, tenant isolation, or a silently disabled control

### 1.1 Idempotency was silently disabled on Postgres for nested writes `FIXED`
`idempotency_keys.key` is `VARCHAR(128)`, but the middleware stored a composite
fingerprint `method|path|header|sha256(body)` — ~168 chars for
`POST /purchase-orders/{uuid}/receipts`. Postgres raised `DataError`, which
`IdempotencyMiddleware` swallowed by design (fail-open, never block a write), so
the write succeeded with **no idempotency and no `Idempotent-Replayed` header**.
Invisible to CI because all 26 test modules use SQLite `create_all`, which does
not enforce `VARCHAR(n)`.

- Fix: migration `0016` widens to `VARCHAR(512)` (metadata-only in PG, no data
  touched) and `_fingerprint()` hashes an over-long value instead of letting it
  overflow. Hashing, not truncating, is deliberate: two long paths differing only
  past the limit must not collide onto one stored response.
- Tests: `test_idempotency_search.py::{test_fingerprint_fits_the_column_for_realistic_paths,
  test_fingerprint_hashes_rather_than_truncates_when_pathological,
  test_long_path_replay_still_works_end_to_end}`

### 1.2 Every non-ollama AI provider could never authenticate `FIXED`
`_provider_key()` was defined but never called, so neither an environment key nor
a per-request BYOK key ever reached a provider. `/ai/providers` advertised
`openai`, `anthropic`, `gemini`, `openrouter` as configured while every call
failed with `no API key for …`.

- Fix: `resolve()` resolves `request key > env > fail-closed` once per request and
  raises one actionable sentence naming the provider and the env var.
- Tests: `test_ai.py::{test_env_key_is_used_when_no_request_key,
  test_request_key_overrides_env_and_header_wins, test_missing_key_names_the_env_var_and_the_provider,
  test_base_url_override_is_honoured, test_provider_catalog_never_leaks_keys}`

### 1.3 Partial invoicing was held forever by three match dimensions `FIXED`
Three separate dimensions of the 11-dim engine made a normal partial payment fail:

| Dim | Old rule | Consequence |
| --- | --- | --- |
| `duplicates` | `prior_invoice_count > 0` | the **second** invoice of any partially-paid PO was a duplicate |
| `totals` | `po_total == inv_total` | any invoice for less than the full order failed |
| `quantities`/`prices` | paired lines **by index** | an invoice listing its lines in a different order than the PO compared the wrong lines |

- Fix: `duplicates` is now a real double-billing test (cumulative invoiced qty vs
  ordered, plus exact `(po_line, qty, price)` re-bills). `totals` is
  `0 < inv_total <= po_total` — over-billing is still a hard fail. Lines pair by
  `po_line_id`, falling back to index only when ids are absent.
- Tests: `test_matching.py::{test_partial_invoicing_stays_clean,
  test_duplicate_billing_is_still_caught, test_over_billing_is_caught_by_totals,
  test_lines_pair_by_id_not_by_position}`

### 1.4 Every award recorded zero savings `FIXED`
The savings baseline was computed **after** the losing quotes were flipped to
`rejected`, and the re-query asked for `status in ("evaluated","awarded")` — so
the comparison set was the winner alone. `savings_records` was therefore always
empty, and the number the savings engine and the copilot both report was always
zero. No test asserted it.

- Fix: the baseline is captured before any status flips, in one grouped query
  (which also removed a query per competing quote).
- Test: `test_sourcing.py::test_award_records_real_savings`

### 1.5 Approval tiers were consumed in arbitrary order `FIXED`
`approve_po` read `pend[0]` off an **unordered** result while the comment
claimed "manager→finance→legal order enforced by tier list". The tier list was
never used for ordering, so a finance approver could consume the manager's
signature slot and skip a step.

- Fix: `services/purchase.py::order_pending()` ranks by `TIER_ORDER`, then
  `created_at`, then `id`.
- Test: `test_approvals.py::test_tiers_are_cleared_in_order_not_row_order`

### 1.6 A finance approver could skip the manager entirely — dead end `FIXED`
`approvals` was **write-only**: no `GET` existed. A submitted requisition's
approvals could not be listed, and no code path could decide a
`resource="requisition"` row, so a requisition could never leave `submitted`.
`REQ_STATUSES.approved/rejected/ordered` were unreachable.

- Fix: `GET /approvals` (keyset, approver-role gated) and
  `POST /approvals/{id}/decide`, which syncs the parent document. The AI and
  purchase routes now share one `decide_approval`, so SoD, tier order and audit
  cannot drift apart again.
- Tests: `test_approvals.py` (11 tests)

### 1.9 The spend cube silently under-reported `FIXED`
The cube inner-joined `spend_transactions` to `purchase_orders` with **no tenant
predicate in the `ON` clause** (relying on RLS alone for join correctness) and
inner semantics, so any ledger row whose PO was missing vanished from the one
number that must never be wrong.

- Fix: outer join, tenant predicate in `ON`, and the orphan is flagged
  (`orphaned: true`) rather than hidden.

---

## 2. S2 — wrong answers, stranded users, unreachable data

### 2.1 Quarantined documents stayed searchable `FIXED`
`/documents/search` never joined `documents`, so a document explicitly held for
review (integrity-failure or hash-mismatch quarantine) kept surfacing in search
results. Both quarantine paths return before the chunk delete.
Test: `test_idempotency_search.py::test_quarantined_documents_are_not_searchable`

### 2.2 `documents.resource_id` was silently truncated `FIXED`
The upload path did `resource_id.strip()[:36]`, storing an id that matched no
record at all. Now a 422 with a length, never a wrong pointer.

### 2.3 The unread feed truncated itself and could dead-end `FIXED`
`?unread=true` over-fetches 4x then filters read-state in Python (`read_by` is a
JSON array with no portable "does not contain"). Two bugs:

- when the over-fetch filled up, discarded rows may have contained unread items
  and `hasMore` still reported `false` — real alerts hidden behind a short page;
- when the filter emptied the page, there was no returned row to anchor a cursor
  to, so `hasMore: true` shipped **with no `nextCursor`** — a dead end.

- Fix: `saturated` forces `hasMore`, and the cursor comes from the last row
  *scanned*, not the last row *returned*.
- Test: `test_notifications.py::test_unread_page_never_reports_hasmore_false_while_rows_remain`

### 2.4 The notification badge was unbounded `FIXED`
`unread-count` loaded **every** broadcast row in the tenant as a full entity, with
no `LIMIT`, on a 30-second poll from every open tab — the most expensive query in
the product. Now selects only `read_by`, capped at `BROADCAST_SCAN_CAP`, and
reports `unreadCapped` rather than quietly truncating.
Test: `test_notifications.py::test_badge_does_not_grow_without_bound`

### 2.5 The same webhook could fire twice `FIXED`
`webhook_endpoints.url` has no unique constraint, and `fanout` delivered to every
matching row — so registering one URL twice sent the same signed payload twice, a
duplicate side effect for any non-idempotent consumer. Duplicates are now
collapsed and reported as `skipped_duplicate`.
Test: `test_integrations.py::test_duplicate_endpoint_urls_are_delivered_once`

### 2.6 A slow webhook could pin the request for 10s × N `FIXED`
Each delivery is synchronous with its own 10s timeout, so N dead endpoints held
the caller open for the sum. Added a 20s total budget; endpoints past it are
recorded as `deferred` (a fact about the fanout, so it belongs in the audit
trail) rather than silently dropped.
Test: `test_integrations.py::test_fanout_budget_defers_rather_than_holding_the_request`

### 2.7 Concurrent price evaluation could 500 `FIXED`
`price_cases` has **no unique constraint** behind a `scalar_one_or_none()`, so two
concurrent evaluations on the same PO line raised `MultipleResultsFound`. Now one
scoped query replaces a query per line.

### 2.8 `/spend/price-cases` was the only unpaginated list `FIXED`
Hard-limited to 100 with no cursor and an unstable ordering, so a tenant with
more than 100 cases could only ever see the newest slice. Now keyset-paginated
like every other list endpoint, and the response carries `poId`, `supplierId`
and `createdAt` so a row is actionable.

### 2.9 The budget gate charged the wrong month `FIXED`
Committed spend was measured from `purchase_orders.created_at` (when the PO was
raised) while the ledger records the commitment at **send** time. A PO raised
31 Jan and sent 2 Feb was charged against January's ceiling. Now read from
`spend_transactions` (kind `commitment`), the same single source of truth the
spend cube uses, so budget and actuals cannot diverge.

### 2.10 `check_budget` had a 500 branch on a money path `FIXED`
An unreachable `HTTPException(500)` guarded a value derived from the clock, not
from input. Now a 422 with a code, ahead of use.

### 2.11 The optimizer's explainability was thrown away `FIXED`
The server returns per-supplier `reason`, pro-rated `cost_minor`, `share_sum_bp`
and `violations`; the UI typed it as `{supplierId, shareBp}` and read only
`.length`. **A share-cap violation was invisible** on a page whose own copy says
"the optimizer proposes a share-capped split". Now rendered as a table with
reasons, and violations as a `role="alert"` block. The plan is cleared when a
different RFQ is opened, so a proposal can never be shown against the wrong RFQ.

### 2.12 Price-evaluate reported a reason it never received `FIXED`
The UI claimed every skipped line was skipped for "no history". The server
returns `PRICE_CASE_OPEN`, `PRICE_NO_HISTORY`, `PRICE_THIN_HISTORY`,
`PRICE_ITEM_INVALID` or `PRICE_BASELINE_INVALID`. The actual reasons are now
surfaced. Also removed an `evaluated?: number` field the server never returned,
and corrected `skipped[].line` from `string` to `number`.

### 2.13 `/ai/providers` shape did not match its own UI `FIXED`
Returned `list[str]`; the copilot typed it `{name, configured}[]`, so every
provider rendered as `undefined (not configured)` above the composer on every
load. Now `{name, configured, needsKey, active}`.

### 2.14 The copilot was the only page with no auth gate `FIXED`
Every other page renders `<AuthScreen>`; the copilot did not, so an
unauthenticated visitor got a live composer that 401'd into `Bearer `.

### 2.15 One bad SSE frame destroyed a good answer `FIXED`
`JSON.parse` was unguarded, so a single malformed frame threw into the outer
catch and the user saw "No answer produced" instead of the answer they had. Also
fixed: no `AbortController` (leaked connection, `setState` after unmount), raw
HTTP status instead of `friendly()` copy, and a stream that ended **without its
evidence frame** being treated as a finished answer.
Tests: `frontend/lib/ai.test.ts` (11 tests)

### 2.16 The robots policy contradicted itself `FIXED`
`robots.ts` stated every route is behind Keycloak so "allowing crawlers to walk
the site buys nothing", then emitted `allow: "/"` and published a sitemap of
thirteen login-walled routes including `/copilot`. The comment now matches the
policy: disallow all, no app sitemap. The route inventory is still exported for
build-time checks.

### 2.17 Three destinations were only reachable via the command palette `FIXED`
The sidebar listed 9 of 13 workspaces; Requisitions, the Negotiation simulator
and Integrations were reachable only with `Ctrl+K`.

---

## 3. Encoding

### 3.1 Every sidebar icon shipped as mojibake `FIXED`
`Shell.tsx` carried triple-encoded UTF-8: the entire icon set, the theme toggle,
the bell and the search trigger rendered as garbage. 13 glyphs recovered
byte-for-byte from the committed bytes; two destroyed by a lossy conversion
(Copilot, Alerts) were replaced from the same geometric family.

### 3.2 The guard that was supposed to catch it missed four real cases `FIXED`
`scripts/check_mojibake.py` shipped a pattern that did not include U+20AC, so it
missed `a-tilde + U+20AC` — the single most common mojibake sequence — and
reported the tree clean while `CommandPalette.tsx` (3 lines) and `sitemap.ts`
(1 line) were still corrupt.

- Fix: the pattern now anchors on the *pair* (an A-circumflex/tilde/grave lead
  immediately followed by a cp1252 remap), which cannot fire on a legitimate
  em dash, ellipsis, curly quote or `e-acute`. The file's own examples are
  escape-encoded so it cannot flag itself.
- **The guard now self-tests.** 19 cases run on every invocation, because a guard
  that cannot detect its own target is worse than no guard.

### 3.3 The CI secret guard could never pass `FIXED`
`.github/workflows/ci.yml` ran
`! grep -R --exclude-dir=.git -Ei "sk-(live|proj)|aws_secret|BEGIN (RSA )?PRIVATE KEY" .`
— the pattern appeared **literally in the workflow's own command line**, so the
guard matched itself and exited 1. It had been red on every run; nobody noticed
because CI is weekly and manual. It also scanned `.kilo/worktrees/`, a stale
worktree copy of this repository that is on disk but not tracked, so a
credential would have been reported from a file nobody committed. Two test
fixtures (`sk-live-123`, `sk-live-raw`) matched the pattern as well.

- Fix: `scripts/check_secrets.py`. Scans tracked files only, skips vendored and
  worktree trees, matches credential *shapes* rather than the word "secret", and
  has an explicit `PLACEHOLDER` allowlist so `.env.example` and the docs pass.
- **It self-tests** (16 cases) and asserts it does not flag its own source —
  the same class of bug it was written to replace.

---

## 4. S3 — performance, maintainability, clarity

| # | Item | Status |
| --- | --- | --- |
| 4.1 | `price_intel.baseline_for` loaded the tenant's **entire** `purchase_order_lines` table per call and is called once per PO line. Added `BaselineCache`, shared across the request | `FIXED` |
| 4.2 | `/rfqs/{id}/comparison` was 2N+1 queries, materialising every `QuoteLine.id` just to count them. Two grouped queries now | `FIXED` |
| 4.3 | `POST /purchase-orders/{id}/receipts` issued a query per prior receipt | `FIXED` |
| 4.4 | `spend_intel.leakage()` loaded every approved/paid `Invoice` entity in the tenant into memory. Done in SQL | `FIXED` |
| 4.5 | The AI gateway had **four** duplicated provider lookups. One `PROVIDERS` table so `complete`, `stream` and `/ai/providers` cannot drift | `FIXED` |
| 4.6 | The copilot hand-rolled its own `fetch`, token read and error string, bypassing the 401 refresh. Extracted to `lib/ai.ts` | `FIXED` |
| 4.7 | The CI secret guard matched its own pattern and could never pass; replaced by a self-testing script (§3.3) | `FIXED` |
| 4.8 | `audit_events.approval` was plumbed from the model to the writer and populated by **no caller**, so no audit row could say which approval authorised a change. Now set on every decision — and it is inside the hashed payload | `FIXED` |
| 4.9 | `spend_intel.maverick` reported `reason: "uncategorized-no-requisition"`, claiming a requisition check that does not exist. The label now states what was tested | `FIXED` |
| 4.10 | `mypy`: 12 errors → **0** | `FIXED` |
| 4.11 | `ruff`: unused imports cleared across `app/` and `tests/` | `FIXED` |
| 4.12 | 22 `E741` (`l` as a variable name) remain — pre-existing style, not in CI, and renaming them across 10 files is churn with regression risk | `OPEN` |
| 4.13 | The copilot builds its own `fetch` path and the command palette re-declares the same 13 destinations as `Shell.NAV`. Two lists that must agree and are not derived from one another | `OPEN` |
| 4.14 | `analytics`/`metrics` is a hand-rolled in-process counter with a 4096-entry latency deque. No OTEL, no Prometheus exporter | `DEBT` |

---

## 5. Blocked — needs a decision or a data pass

### 5.1 Zero foreign keys, anywhere `BLOCKED`
40 tables, **no `FOREIGN KEY` constraint and no `relationship()`**. Every link is
a bare `*_id` string. Application-level validation now covers the nine columns
that had none (`services/refs.py`), and the app already validated the rest — but
nothing stops an out-of-band writer, an admin tool or a future migration from
creating an orphan.

Why blocked: a real constraint needs a data-cleanliness pass first. Any existing
dangling id turns `ADD CONSTRAINT` into a failed deploy, and a `NOT VALID` +
`VALIDATE` split is the only safe way to stage it. **This is the single
highest-value schema change available** and needs a decision.

### 5.2 Three tables are entirely dead `OPEN`
`organizations`, `user_accounts`, `roles` — never read or written. Authorization
is a hard-coded `WRITE_ROLES` set per router, so `roles.permissions` is
decorative. RBAC lands with the identity work. `organizations`/`user_accounts` are
also the reason `notifications.user_sub` has no local referential target.

### 5.3 Three tables are write-only `OPEN`
`integrations` (the adapter registry is a hard-coded dict, so `settings` and
`secret_ref` are stored and ignored), `contract_signatures` and `match_runs`
(evidence written, never readable). No dispute or audit path consumes them.

### 5.4 `purchase_orders` has no `requisition_id` `OPEN`
`spend_intel.py` and `models/purchase.py` both describe a
requisition → PO lineage; the column does not exist, so `create_po` takes no
requisition reference and **the maverick metric is really an "uncategorised PO"
metric**. An award also has no link to the PO it produced. This needs a
migration plus every write path — hence the honest `reason` string in §2.8's
sibling fix rather than a fabricated claim.

### 5.5 `CREATE EXTENSION vector` is required and never used `OPEN`
Installed at migration 0001, referenced by no column, index or query. Embeddings
are JSON arrays ranked with in-Python cosine. It is an install-time dependency on
pgvector for nothing.

### 5.6 An invoice or PO can never be rejected `OPEN`
`INVOICE_STATUSES` `matched`/`paid`/`rejected` and `PO_STATUSES`
`invoiced`/`closed`/`cancelled` are unreachable: only `approve` exists. A bad
invoice is therefore **permanently stuck at `received`**. This is a missing
capability rather than a broken one, so it is listed rather than silently added.

### 5.7 `services/contract.py` promises a `renewed_from` link that does not exist `OPEN`
The docstring advertises contract renewal via a successor link; there is no such
column and no code path.

### 5.8 All search is leading-wildcard `ILIKE` `OPEN`
So the purpose-built name indexes (`ix_supplier_tenant_name`, …) are unusable and
`document_chunks.text` has no index at all. Fixing it properly means `pg_trgm`
GIN indexes — an additive migration, but one that needs a decision on the
extension dependency (§5.5).

### 5.9 No CI on push or pull request `DEBT`
CI is weekly + manual dispatch only, by owner budget. Nothing gates a merge.

---

## 6. Test and verification gaps

| # | Gap | Severity |
| --- | --- | --- |
| 6.1 | **All 26 test modules build the schema with `create_all` on SQLite.** Neither Alembic nor `VARCHAR(n)` nor RLS is exercised. This is the blind spot that hid §1.1 | S1 |
| 6.2 | The live Postgres chain (`upgrade → check → downgrade → upgrade`) could not be run locally — Docker Desktop would not start. Verified offline instead: `alembic upgrade head --sql` against the Postgres dialect renders one head and 275 statements with no destructive step | S2 |
| 6.3 | No frontend test covers any page component. The copilot, RFQ, orders and spend surfaces had zero coverage, which is why §2.11–2.14 shipped green | S2 |
| 6.4 | `api<T>()` is a generic with no runtime validation, so any response-shape mismatch is invisible to `tsc`. §2.13 and §2.12 were both of this kind | S2 |
| 6.5 | No load test is wired into CI (`backend/scripts/load_test.py` exists but is manual) | S3 |

---

## 7. Verification baseline (this commit)

| Gate | Result |
| --- | --- |
| `pytest backend/tests` | **141 passed** (was 113) |
| `npm run typecheck` | clean |
| `npm run lint` | 0 errors, 5 pre-existing warnings |
| `npm test` | **48 passed** (was 37) |
| `npm run build` | 18 routes, green |
| `mypy backend/app` | **0 errors** (was 12) |
| `ruff check` | clean apart from 22 pre-existing `E741` |
| `alembic heads` | single head `0016`, no destructive `upgrade()` |
| `check_mojibake.py` | clean, 530 files, 19 self-test cases |
| `check_secrets.py` | clean, 537 tracked files, 16 self-test cases |
| `verify_brain_links.py` | 85/85 |
| `api/openapi.json` | regenerated, no drift |

---

## 8. Contributing to this file

When you fix something, move the entry to `FIXED` and record **the test that
fails without the fix**. A fix with no regression test is a wish. When you find
something new, add it with a severity and a one-line "why it matters" — a bug
register that only lists defects, without consequences, becomes a backlog nobody
reads.
