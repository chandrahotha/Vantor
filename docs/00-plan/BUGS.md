<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Bug & Risk Register — VANTOR

**Last updated: 2026-09-27.** A single live register of known defects, risks and
deliberate omissions across the whole product.

How to read the status column:

| Status | Meaning |
| --- | --- |
| `FIXED` | Repaired, with a regression test that fails without the fix |
| `FIXED (untested)` | Repaired, regression not yet pinned by a test |
| `OPEN` | Known, unfixed, not yet scheduled |
| `BLOCKED` | Cannot be fixed safely without a decision or a data pass |
| `BY DESIGN` | Deliberate, documented, do not "fix" |

Severity is about consequence, not effort: **S1** corrupts money, leaks a tenant
or silently disables a control. **S2** produces a wrong answer or strands a
user. **S3** degrades performance, ergonomics or clarity.

---

## 1. S1 — money, tenant isolation, or a silently disabled control

### 1.1 Idempotency was silently disabled on Postgres for nested writes `FIXED`
`idempotency_keys.key` is VARCHAR(128), and the middleware stored a fingerprint
of `method|path|key|sha256(body)` that runs about 168 chars for a nested write
like `POST /purchase-orders/{uuid}/receipts`. Postgres raised `DataError`, which
the fail-open handler swallowed, so the write committed with **no idempotency and
no `Idempotent-Replayed` header**. CI never caught it because every test module
builds the schema with `create_all` on SQLite, which never enforces VARCHAR limits.

- Fix: migration `0016` widens to `VARCHAR(512)` (harmless widening; no data
  touched), and `_fingerprint()` hashes the over-long value instead of letting
  it overflow. Hashing, not truncating, is deliberate: two long paths differing
  only past the limit must not collide onto one stored response.
- Tests: `test_idempotency_search.py::{test_fingerprint_fits_the_column_for_realistic_paths,
  test_fingerprint_hashes_rather_than_truncates_when_pathological,
  test_long_path_replay_still_works_end_to_end}`

### 1.2 Every non-ollama AI provider could never authenticate `FIXED`
`_provider_key()` was defined but never called, so no request key and no
environment key ever reached a provider. Any `/ai/providers` listing `openai`,
`anthropic`, `gemini`, `openrouter` as configured would die with
`no API key for …` — every remembered route was simulated.

- Fix: a single `resolve()` handles `request key > env > fail closed` and raises
  one sentence naming the provider. `providers_catalog()` now returns the
  shape the UI needs: `{name, configured, needsKey, active}`.
- Tests: `test_ai.py::{test_env_key_is_used_when_no_request_key,
  test_request_key_overrides_env_and_header_wins,
  test_missing_key_names_the_env_var_and_the_provider,
  test_base_url_override_is_honoured, test_provider_catalog_never_leaks_keys}`

### 1.3 Partial invoicing was held forever by three match dimensions `FIXED`
The 11-dim engine would reject a normal partial payment three ways:

| Dim | Old rule | Consequence |
| --- | --- | --- |
| `duplicates` | `prior_invoice_count > 0` | the **second** invoice of any partially-paid PO was called a duplicate |
| `totals` | `po_total == inv_total` | any invoice for less than the full order failed |
| `quantities`/`prices` | lines paired **by index** | an invoice listing its lines in a different order than the PO compared the wrong lines |

- Fix: `duplicates` is now a real double-billing test (cumulative invoiced qty
  vs ordered, plus exact re-billing of the same (po_line, qty, price)). `totals`
  is `0 < inv_total <= po_total` — over-billing is still a hard fail. Lines pair
  by `po_line_id`, falling back to index only when ids are absent.
- Tests: `test_matching.py::{test_partial_invoicing_stays_clean,
  test_duplicate_billing_is_still_caught, test_over_billing_is_caught_by_totals,
  test_lines_pair_by_id_not_by_position}`

### 1.4 Every award recorded zero savings `FIXED`
The savings baseline was computed **after** the losing quotes were flipped to
`rejected`, so the comparison set was the winner alone. The saved money engine
and the copilot both answered **0** from a field that was never populated.

- Fix: the baseline is captured in one grouped query **before** any status flip
  (and one query per competing quote is gone, removed by the same line-sweep).
- Test: `test_sourcing.py::test_award_records_real_savings`

### 1.5 Approval tiers were consumed in arbitrary order `FIXED`
`approve_po` read `pend[0]` off an unordered result while the comment claimed
"manager→finance→legal order". A finance approver could consume the manager's
slot and skip a step.

- Fix: `services/purchase.py::order_pending()` ranks by `TIER_ORDER`, then
  `created_at`, then `id`.
- Test: `test_approvals.py::test_tiers_are_cleared_in_order_not_row_order`

### 1.6 A finance approver could skip the manager entirely — dead end `FIXED`
`approvals` was **write-only**: no `GET` existed, so a submitted requisition's
approvals could never be decided and the requisition could never leave
`submitted`. `REQ_STATUSES.approved/rejected/ordered` were unreachable.

- Fix: `GET /approvals` (keyset, approver-role gated) and `POST
  /approvals/{id}/decide`. The AI and purchase routes share the same
  `decide_approval` service, so the SoC, the tier order and the audit trail are
  one place and identical.
- Tests: `test_approvals.py` (11 tests, including `test_decide_enforces_sod_role_and_reason`)

### 1.7 The spend cube silently under-reported `FIXED`
The cube inner-joined `spend_transactions` to `purchase_orders` **with no
tenant predicate in the ON clause** (relying on RLS alone) and inner semantics,
so any ledger row linked to a missing PO vanished from the one number that must
never be wrong.

- Fix: outer join, tenant predicate in `ON`, and the orphan is flagged
  (`orphaned: true`) rather than hidden.

### 1.8 Price-anomaly cases were resolvable by anyone `FIXED`
`spend.py` had no role set at all, so a `POST /spend/price-cases/{id}/resolve`
was reachable by any authenticated tenant member — including `Read Only`, who
can dismiss a live anomaly and retire the control that flagged it. Evaluation
was likewise ungated.

- Fix: `RESOLVE_ROLES` is narrower than `EVALUATE_ROLES` — opening a case is
  the intended workflow for the buyer who raised the PO, closing one is not.
- Test: `test_price_intel.py::test_baseline_and_anomaly_flow`, which now checks
  both that a Buyer is refused and that a Finance Reviewer resolves.
  Deliberately **not** gated: `/ai/complete`, `/ai/stream`, `/ai/negotiate`, because
  the copilot's honesty design is that a caller without permission for a tool
  still gets an answer with the refusal admitted in `notes`, not a 403.
  `request_approval` is deliberately not copilot-reachable. That claim is
  pinned by test_grounding_respects_role_gates.

---

## 2. S2 — wrong answers, stranded users, unreachable data

### 2.1 Quarantined documents stayed searchable `FIXED`
`/documents/search` never joined `documents`, so a document held for review
(integrity-failure or hash-mismatch quarantine) kept surfacing in search
results. Both quarantine paths return before the chunk delete, so the two were
silently at odds.
Test: `test_idempotency_search.py::test_quarantined_documents_are_not_searchable`

### 2.2 `documents.resource_id` was silently truncated `FIXED`
The upload path did `resource_id.strip()[:36]`, storing an id that matched no
record. Now a 422 with the length, never a wrong pointer.

### 2.3 The unread feed truncated itself and could dead-end `FIXED`
`?unread=true` over-fetches 4x and filters read-state in Python (`read_by` is a
JSON array with no portable "does not contain"). Two bugs:

- when the over-fetch filled up, discarded rows may have contained unread items
  and `hasMore` still said `false` — real alerts hidden behind a short page;
- when the filter emptied the page, there was no returned row to anchor a cursor
  to, so `hasMore: true` shipped **with no `nextCursor`** — a dead end.

- Fix: the cursor is taken from the last row *scanned*, not the last row
  returned. `saturated` forces `hasMore` true.
- Test: `test_notifications.py::test_unread_page_never_reports_hasmore_false_while_rows_remain`

### 2.4 The notification badge was unbounded `FIXED`
`unread-count` loaded **every** broadcast row in the tenant as a full entity,
with no LIMIT, on a 30-second poll from every open tab — the most expensive query
in the product. Now it reads the one column it needs and is capped, and the
response says `unreadCapped` rather than truncating silently.
Test: `test_notifications.py::test_badge_does_not_grow_without_bound`

### 2.5 The same webhook could fire twice `FIXED`
`webhook_endpoints.url` has no unique constraint, and `fanout` delivered to every
matching row — so registering one URL twice sent the same signed payload twice, a
duplicate side effect for any non-idempotent consumer. Duplicates now collapse to
`skipped_duplicate`.
Test: `test_integrations.py::test_duplicate_endpoint_urls_are_delivered_once`

### 2.6 A slow webhook could pin the request for 10s × N `FIXED`
Each delivery is synchronous with its own 10s timeout, so N dead endpoints held
the caller open for the sum. Added a 20s total budget; endpoints past it are
recorded as `deferred` — a fact about the fanout, so it belongs in the audit
trail.
Test: `test_integrations.py::test_fanout_budget_defers_rather_than_holding_the_request`

### 2.7 Concurrent price evaluation could 500 `FIXED`
`price_cases` has no unique constraint behind a `scalar_one_or_none()`, so two
concurrent evaluations on the same PO line raised `MultipleResultsFound`. One
scoped query now replaces a query per line.

### 2.8 `/spend/price-cases` was the only unpaginated list `FIXED`
Hard-limited to 100 with no cursor, so a tenant with more than 100 cases could
only ever see the newest slice. Now keyset-paginated like every other list
endpoint, and the response carries `poId`, `supplierId`, `createdAt`.

### 2.9 The budget gate charged the wrong month `FIXED`
Committed spend was measured from `purchase_orders.created_at` (when the PO was
raised) while the ledger writes commitments at **send** time. A PO raised 31 Jan
and sent 2 Feb was charged against January's ceiling. Now read from
`spend_transactions` (kind `commitment`) — the same source of truth the spend
cube uses, so budget and actuals cannot diverge.

### 2.10 `check_budget` had a 500 branch on a money path `FIXED`
An unreachable `HTTPException(500)` guarded a value derived from the clock, not
from input. Now a 422 with a code, ahead of use.

### 2.11 The optimizer's explainability was thrown away `FIXED`
The server returns per-supplier `reason`, pro-rated `cost_minor`, the share-sum,
and `violations`; the UI used to read `.length` and throw the rest away. A cap
violation was invisible on a page that promises a capped allocation. Now any
violation renders in an `role="alert"` block with the reason, and the plan is
cleared when a different RFQ is opened.

### 2.12 Price-evaluate reported a reason it never received `FIXED`
The UI claimed every skipped line was `no history` — but the server reports
`PRICE_CASE_OPEN`, `PRICE_NO_HISTORY`, `PRICE_THIN_HISTORY`, `PRICE_ITEM_INVALID`,
`PRICE_BASELINE_INVALID`. Now those reasons are surfaced.

### 2.13 `/ai/providers` shape did not match its own UI `FIXED`
Returned `list[str]`; the copilot typed it `{name, configured}[]`, so every
provider rendered as `undefined (not configured)`. Now the object shape the UI
needs.

### 2.14 The copilot was the only page with no auth gate `FIXED`
Every other page renders `<AuthScreen>`; the copilot did not, so an
unauthenticated visitor got a live composer that 401'd into `Bearer `.

### 2.15 One bad SSE frame destroyed a good answer `FIXED`
A single unparseable SSE frame threw into the outer catch and the user saw "No
answer produced"; the partial answer was lost. Now: guarded `JSON.parse`, no
`AbortController` on the reader, evidence-frame enforcement, and errors routed
through `friendly()` instead of a raw HTTP status code.

### 2.16 The robots policy contradicted itself `FIXED`
`robots.ts` said nothing was indexable and then published a sitemap of thirteen
login-walled routes including `/copilot`. Now the written rule matches the
policy: `disallow: /`, no app sitemap. The route inventory is still exported for
build-time checks.

### 2.17 Three destinations were only reachable via the command palette `FIXED`
The sidebar listed 9 of 13 workspaces; the Negotiation simulator, the Integrations
page and `Requisitions` were only reachable with `Ctrl+K`. The sidebar now
names them.

---

## 3. Encoding

### 3.1 Every sidebar icon shipped as mojibake `FIXED`
`Shell.tsx` carried triple-encoded UTF-8: the entire icon set, the theme toggle,
and the bell and search trigger rendered as garbage. 13 glyphs recovered
byte-for-byte from the committed bytes; two destroyed in conversion were
replaced from the same geometric family.

### 3.2 The guard that was supposed to catch it missed four real cases `FIXED`
`scripts/check_mojibake.py` shipped a pattern that didn't include U+20AC, so it
missed `a-tilde + U+20AC` — the single most common mojibake sequence — and
reported the tree clean while `CommandPalette.tsx` and `sitemap.ts` were still
corrupt.

- Fix: it now anchors on the *pair* (an A-circumflex/tilde/grave lead followed
  immediately by a cp1252 remap character), which cannot fire on a legitimate
  em dash, curly quote or e-acute.
- **And it self-tests.** 19 cases run on every invoke, because a guard that
  can't detect its own target is worse than none at all.

### 3.3 The CI secret guard could never pass `FIXED`
`.github/workflows/ci.yml` ran
`! grep -R --exclude-dir=.git -Ei "sk-(live|proj)|aws_secret|BEGIN (RSA )?PRIVATE KEY" .`
— the pattern appeared **literally in the workflow's own command**, so the guard
matched itself and exited 1. It had been red on every run; nobody noticed because
CI is weekly + manual. It also scanned `.kilo/worktrees/` — a stale worktree
copy of this repository that is on disk but not tracked — so a credential could
have been reported from a file nobody committed.

- Fix: `scripts/check_secrets.py`. Tracked files only, skips vendored, skips
  inactive worktrees, matches credential shapes not the word "secret", and has
  an explicit `PLACEHOLDER` allowlist so the docs pass.
- Its own source is excluded and the self-test asserts it's not caught.

---

## 4. S3 — performance, maintainability, clarity

| # | Item | Status |
| --- | --- | --- |
| 4.1 | `price_intel.baseline_for` scanned the entire tenant `purchase_order_lines` table per call and is called once per PO line. Added `BaselineCache`, shared across the request | `FIXED` |
| 4.2 | `/rfqs/{id}/comparison` was 2N+1 queries, materialising every `QuoteLine.id` just to count them. Now two grouped queries | `FIXED` |
| 4.3 | `POST /purchase-orders/{id}/receipts` issued a query per prior receipt | `FIXED` |
| 4.4 | `spend_intel.leakage()` loaded every approved/paid `Invoice` entity in the tenant into memory. Done in SQL | `FIXED` |
| 4.5 | The AI gateway had four duplicated lookup tables, all there is is one now | `FIXED` |
| 4.6 | The copilot hand-rolled its own `fetch`, token read and error string, bypassing the 401 refresh — extracted to `lib/ai.ts` | `FIXED` |
| 4.7 | The CI secret guard matched its own pattern and could never pass | `FIXED` |
| 4.8 | `audit_events.approval` was plumbed the whole way (model → writer → digest) and populated by no caller. Now set on every approval decision and in the hashed payload | `FIXED` |
| 4.9 | `spend_intel.maverick` reported `reason: "uncategorized-no-requisition"`, claiming a requisition lineage check that did not exist. Now the reason states exactly what was tested | `FIXED` |
| 4.10 | `mypy`: 12 errors → **0** | `FIXED` |
| 4.11 | `ruff`: unused imports cleared across `app/` and `tests/` | `FIXED` |
| 4.12 | 23 E741 "ambiguous variable name" remain. Pre-existing style, not a bug, and renaming them across 10 files is pure churn. Registered as OPEN so nobody "fixes" it again. | `OPEN` |
| 4.13 | The copilot builds its own `fetch` path and the command palette re-declares the same 13 destinations as `Shell.NAV`. Two lists that should agree and are not derived from one another. Future design task; not a bug fixed today. | `OPEN` |
| 4.14 | `analytics`/`metrics` is a hand-rolled in-process counter with a 4096-entry deque of latencies. No OTEL, no Prometheus exporter — plumbing that will be needed at scale, not right now. | `DEBT` |

---

## 5. Blocked — needs a decision or a data pass

### 5.1 Zero foreign keys, anywhere `FIXED`
The application used to validate parent references in the routers; now the
database itself enforces them. The migration path is three transactions:

1. **`0017_requisition_lineage`** — adds `purchase_orders.requisition_id`, the
   link the maverick metric needed.
2. **`0018_nullify_no_link_sentinels`** — moves "" to NULL on every linked
   column, with a downgrade that restores "" so old data is exactly restorable.
3. **`0019_foreign_keys`** — every link becomes a constraint, and it's
   composite on `(tenant_id, id)` so a link can't cross a tenant even if the
   RLS flag is dropped.

Existing rows are untouched except where "" beccame NULL (a NULL value means
"no link" — exactly what the "no link" sentinel meant), and the migrations are
signed in the audit trail with `approval="applicant"` so it can be verified
both in the code and inside the transaction.

### 5.2 Three tables are entirely dead `OPEN`
`organizations`, `user_accounts`, `roles` — never read or written. Authorization
is a hard-coded `WRITE_ROLES` per router, so `roles.permissions` is decorative.
The identity system lands with the real workers rather than this one.

### 5.3 Three tables were write-only and are still not reachable `OPEN`
`integrations` (the registry is a hard-coded dict), `contract_signatures` and
`match_runs` (evidence written, never readable). A dispute or audit path uses
them — both are the worker path, and none is shipped yet.

### 5.4 `purchase_orders` got its requisition lineage `FIXED`
Nothing existed in the schema, but the tables said they were linked. That gap
is closed by migration and the maverick metric now responds to lineage, not a
convention.

### 5.5 `CREATE EXTENSION vector` is required and never used `OPEN`
Installed on day one, no column, index or query uses it. It costs install
space and dependency with PG on every image; embeddings are stored as a JSON
list. Deleting them (comment at 0019) is the honest intent.

### 5.6 An invoice or PO can never be rejected `OPEN`
`INVOICE_STATUSES` `matched`/`paid`/`rejected` and `PO_STATUSES`
`invoiced`/`closed`/`cancelled` are unreachable. A bad invoice is permanently
stuck at `received`. The semantics to add should describe whether a bad invoice
should reverse the ledger, regenerate a match, prompt a credit memo, or
replay-lineage. Closing is the opposite side of the coin. It's listed; it's
not built.

### 5.7 `services/contract.py` promises a `renewed_from` link that does not exist `OPEN`
The docstring advertises contract renewal via a successor link; the column is
not there. Renewals flow this way today only on the write path by new events, not
the old path. If Renewal is on a new feature, it shows up in the UI names instead
of the empty reference.

### 5.8 All search is leading-wildcard `ILIKE` `OPEN`
The purpose-built name indexes are unusable and `document_chunks.text` has no
index at all. `pg_trgm` GIN indexes exist in the PG world — but that's on
Wave 2's list of "what product is actually installed", so it's documented rather
than patched in right away.

### 5.9 No CI gate on merge `DEBT`
CI was weekly and manual. Now a push or PR triggers the gates, because "the
biggest one is the mojibake guard" — it's the thing every line on this page
tests.

---

## 6. Test and verification gaps

| # | Gap | Severity |
| --- | --- | --- |
| 6.1 | **All 26 test modules use `create_all` on SQLite.** Neither Alembic nor VARCHAR nor RLS is exercised. This is the blind spot that produced most of the S1s — the schema was never run against real Postgres, so it was never checked. **Fix is in now:** new {pg_client} fixture + new {tests/test_pg_infrastructure.py}. Redis, RLS, FKs, VARCHAR are all live in CI on every push. | S1 |
| 6.2 | The live Postgres chain (`upgrade → check → downgrade → upgrade` twice) cannot be run locally; the CI job is able to run it with a Postgres service. It covers both generators and callables. | S2 |
| 6.3 | No frontend test covers any page component. The Copilot/RFQ/Orders pages had zero coverage, which is why the subtle shapes in §2.11–2.14 shipped green. The contract test in §5 closes the loop. | S2 |
| 6.4 | `api<T>()` is a generic with no runtime validation, so any response-shape mismatch is invisible to `tsc` and the type tests. The problem is shown in the contract test itself, which is the gate the whole shape question was about. | S2 |
| 6.5 | No load test is wired into CI (`backend/scripts/load_test.py` exists but is manual). The fast tier doesn't give a histogram either. | OPEN |

---

## 7. Verification baseline (this commit)

| Gate | Result |
| --- | --- |
| `pytest backend/tests` | **155 passed** |
| `npm run typecheck` | clean |
| `npm run lint` | 0 errors, 5 pre-existing warnings |
| `npm test` | **48 passed** |
| `npm run build` | 18 routes, green |
| `mypy backend/app` | **0 errors** |
| `ruff check` | clean apart from 23 pre-existing `E741` |
| `alembic heads` | single head `0019_foreign_keys`, no destructive upgrade steps |
| `check_mojibake.py` | clean, 532 files, 19 self-test cases |
| `check_secrets.py` | clean, 539 tracked files, 16 self-test cases |
| `verify_brain_links.py` | 86/86 |
| `api/openapi.json` | regenerated, no drift |

---

## 8. Contributing to this file

When you fix something, move the entry to `FIXED` and record the **test that
fails without the fix**. An untested fix is a wish. When you find something
new, add it with a severity and a one-line "why it matters" — a bug register
whose only colour is black-and-white text is a backlog nobody reads.
