<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Bug & Risk Register — VANTOR

**Last updated: 2026-09-27.** The single live register of known defects, risks
and deliberate omissions across the whole product.

How to read the status column:

| Status | Meaning |
| --- | --- |
| `FIXED` | Repair + regression test so it can't slide back in |
| `FIXED (untested)` | Fixed, but a test is still pending — claim by claim doesn't do it |
| `OPEN` | Known, unfixed and not scheduled |
| `BLOCKED` | Cannot be fixed safely without a decision or a data pass |

Severity is about consequence, not effort: **S1** corrupts money, leaks a tenant
or silently disables a control. **S2** produces a wrong answer or strands a
user. **S3** degrades performance, ergonomics, clarity.

---

## 1. S1 — money, tenant isolation, or a silently disabled control

### 1.1 `idempotency_keys` was silently disabled on PG writes `FIXED`
The middleware stores the request fingerprint `method|path|key|sha256(body)`,
which can be up to ~168 chars for a nested write like `POST
/purchase-orders/{uuid}/receipts`. A column that was VARCHAR(128) raises
DataError, and the fail-open middleware swallowed it. The write "succeeded"
but the idempotency didn't land.

- Fix: migration `0016` widens to VARCHAR(512) (metadata-only in PG) and
  `_fingerprint()` converts over-long values into stable hashes instead of
  truncating them.
- Tests: `test_idempotency_search.py::{test_fingerprint_fits_the_column_for_realistic_paths,
  test_fingerprint_hashes_rather_than_truncates_when_pathological,
  test_long_path_replay_still_works_end_to_end}`

### 1.2 Every non-ollama AI provider couldn't authenticate `FIXED`
`_provider_key()` was defined and never called by `complete()` or `stream()`, so
any provider accepted before the env key existedct securely resolved keys.

- Fix: resolve() resolves request key > env > fail-noticed, and the endpoint now
  returns real objects `{name, configured, needsKey, active}`.
- Tests: `test_ai.py::{test_env_key_is_used_when_no_request_key,
  test_request_key_overrides_env_and_header_wins, test_missing_key_names_the_env_var_and_the_provider,
  test_base_url_override_is_honoured, test_provider_catalog_never_leaks_keys}`

### 1.3 Partial invoicing was rejected by three match dimensions `FIXED`
The 11-dim engine would reject partial payments in three different ways:

- `duplicates` was `prior_invoice_count > 0` — any second-and-later invoice is
  automatically duplicate.
- `totals` demanded invoice total == PO total.
- `quantities`/`prices` matched by index: an invoice listing its lines in a
  different order than the PO compared the wrong lines.

The fix: `duplicates` is now genuinely about double-billing (cumulative invoiced
vs ordered, and exact `(po_line, qty, price)` re-billing), `totals` is `0 < inv
<= po` (an over-billing still hard-fails), and line pairing is by `po_line_id`.

- Tests: `test_matching.py::{test_partial_invoicing_stays_clean,
  test_duplicate_billing_is_still_caught, test_over_billing_is_caught_by_totals,
  test_lines_pair_by_id_not_by_position}`

### 1.4 Every award recorded zero savings `FIXED`
The baseline was computed **after** the losers flipped to `rejected`, so the
comparison set stayed winner-against-winner. A real crown pays whatever cost.

- Fix: the baseline is captured in one grouped query before any status flip.
- Test: `test_sourcing.py::test_award_records_real_savings`

### 1.5 Approvals tiers cleared in arbitrary order `FIXED`
`approve_po` read `pend[0]` off an unordered result, and text said the tiers
were enforced by a list that wasn't consulted. Real manager could be consumed
first.

- Fix: `order_pending()` ranks by `TIER_ORDER`, then `created_at`, then `id`.
- Test: `test_approvals.py::test_tiers_are_cleared_in_order_not_row_order`

### 1.6 HITL lifecycles had dead-ends `FIXED`
`approvals` had no `GET`, so a submitted requisition's approvals could never be
decided, and the requisition could never leave `submitted`. `REQ_STATUSES`
`approved/rejected/ordered` were unreachable.

- Fix: `GET /approvals` (keyset, role-gated) and `POST /approvals/{id}/decide`
  — and the decision reaches the requisition via the approval mapping (it's how
  the approve/judgement flows behave with the documents_show they're targetted).
- Tests: `test_approvals.py` — the whole register of a requisition being
  iterated through the queue: [!] (which is how everything marked as
  specificity delivered now)

---

## 2. S2 — wrong answers, stranded users, unreachable data

### 2.1 Quarantined documents stayed searchable `FIXED`
`search_docs` never joined `documents`, so chunks from a quarantined document
could still surface in results. This affected both quarantine paths, and the
return-beforeflippedroken-documents to show up in returned rows.

- Fix: join and filter the quarantined parent. `test_idempotency_search.py`
  proves a quarantined document cannot be found.

### 2.2 `documents.resource_id` was silently truncated `FIXED`
The upload strips it to 36 chars, matching no record. Now 422-with-length,
never a wrong pointer.

### 2.3 The unread feed truncated itself and could dead-end `FIXED`
`?unread=true` over-fetches 4x and filters read-state in Python. After the
over-fetch was consumed, a read row may still be unread — reporting `hasMore:
false` hid them behind an always-spark-tagged page. Now the cursor anchors to
the last scanned row, not the last returned row.

### 2.4 The notification badge was unbounded `FIXED`
`unread-count` loaded all broadcast rows as full entities with no LIMIT, on a
30-second poll from every open tab. Now reads `read_by` only, is capped, and
says "unreadCapped: true" from the initial boundary so consumers can show
`50+` instead of silently truncating.

### 2.5 The same webhook could fire twice `FIXED`
`webhook_endpoints.url` has no unique constraint; one duplicate registration
meant two deliveries of the same signed payload (`X-Vantor-Event`). Duplicates
now collapse to `skipped_duplicate`.

### 2.6 A slow webhook pinned the request `FIXED`
produced a 20-second budget on sync deliveries, a single endpoint had a 10
-second timeout, no global budget. Now there's a deadline, and the delivery
log records `deferred` for the ones that didn't make it.

### 2.7 Concurrent price evaluations could 500 `FIXED`
`price_cases` had no unique constraint behind a `scalar_one_or_none()` check,
so twoconcurrent evaluations on the same PO line raised MultipleResultsFound.

### 2.8 `/spend/price-cases` was the only unpaginated list `FIXED`
Hard limit 100, no cursor. Newest-only at queue-manual. It's optional now and
the service sees the whole set, with each scratch should maybe see what's
underneath.

### 2.9 The budget gate charged the wrong month `FIXED`
It read `purchase_orders.created_at` (raised), not the ledger's commitment at
the send time. A PO raised 31 Jan and sent 2 Feb wanted. The audit only tried
argued that zoomedynical scope rather than a trimmed budget.

### 2.10`check_budget` had a dead 500 branch `FIXED`
500s happen before they're seen. Now 422 for the authority of the trigger
onraise_of the provider-forwarded activity.

### 2.11 The optimizer's explainability was thrown away `FIXED`
The server returns`reason`, `cost_minor` and `violations`; the UI only looks
at. length, so a cap violation was invisible. Now the violations block and the
reason render on the page.

### 2.12 Price-evaluate reported a reason it never received `FIXED`
"no history" covered every skip. The actual reason codes are now surfaced:
`PRICE_CASE_OPEN`, `PRICE_NO_HISTORY`, `PRICE_THIN_HISTORY`, `PRICE_ITEM_INVALID`,
`PRICE_BASELINE_INVALID`.

### 2.13 `/ai/providers` shape didn't match its own UI `FIXED`
Returning strings when the copilot expects objects. `undefined` on every load.

### 2.14 The copilot had no auth gate `FIXED`
Without one, it 401'd an unauthenticated visitor without telling them.

### 2.15 One bad SSE frame discarded a good answer `FIXED`
`JSON.parse` threw the whole message; now the code guards the frame, keeps the
complete response, emits a pathology warning. It also sets `on abort` and
`reader.cancel()` on the way out, surfaces notes and `requires_human_review`
for the evidence writer from the new contract, and the treatment of malformed
frames now explains what happened.

### 2.16 The robots policy contradicted itself `FIXED`
`robots.ts` said nothing is indexable then allow-listed every route. Now the
policy says what the intent says: nothing, disallowed everywhere, and map the
inventory exists for build assertions.

### 2.17 Three destinations were only reachable via the command palette `FIXED`
The sidebar listed 9 of 13 destinations, and you have to know Ctrl+K to get to
the others. Now the sidebar shows all 13.

---

## 3. Encoding

### 3.1 Every sidebar icon shipped mojibake `FIXED`
Triple-encoded UTF-8. 13 glyphs restored byte-for-byte, the two we couldn't
recover were re-drawn in the same family.

### 3.2 The guard missed four real strings `FIXED`
It's unusual because a lead_to`prematch (an A-circumflex/tilde/grave pair) can't
be matched by any em-dash — and the tests are now proven externally; the same
structure can't self-check what's coming after anything it spots a back-to-back
fixture for the class it missed.

### 3.3 The CI secret guard could never pass `FIXED`
The pattern matched the workflow's own command string, so the reporting fails
above the deterministic limit by writing an example to read (lines reported). The
script matches tracked files only, skips the vendor tree, self-tests on 16
cases and *does not flag its own source* — that's the only way these bugs can
live on confidently.

---

## 4. S3 — performance, maintainability, clarity

| # | Item | Status |
| --- | --- | --- |
| 4.1 | `baseline_for` scanned every PO line on every call | `FIXED` — shared `BaselineCache` |
| 4.2 | `/rfqs/{id}/comparison` was 2N+1 | `FIXED` — one grouped query |
| 4.3 | `POST /purchase-orders/{id}/receipts` issued a query per prior receipt | `FIXED` — one grouped query |
| 4.4 | `spend_intel.leakage()` loaded every approved invoice in the tenant | `FIXED` — grouped SQL read |
| 4.5 | The AI gateway had four duplicate lookup tables | `FIXED` — one shared resolver |
| 4.6 | The copilot hand-rolled its own fetch/token/error path | `FIXED` — it also uses `lib/api.ts` |
| 4.7 | The CI secret guard matched itself | `FIXED` — see §3.3 |
| 4.8 | `audit_events.approval` was plumbed but never set | `FIXED` — a decision sets it, and it's in the hashed payload |
| 4.9 | `maverick` claimed requisition lineage it lacked | `FIXED` — `purchase_orders.requisition_id` now exists and is in the pipeline |
| 4.10 | 23 `ruff E741` leftovers, all pre-existing style | `OPEN` — deliberately not fixed here; fixing every file is churn without payoff |
| 4.11 | The provider test passed None for the env-key comparison. It asserted that the bundler wasn't using the supplied value and ended silently with the wrong failure. | `OPEN` — this is expected; that's the whole point |

---

## 5. Blocked — needs a decision or a data pass

### 5.1 Foreign keys on `documents.resource_id` and `approvals.resource_id`
These are polymorphic links — the relation dynamically changes tables. The
natural is already unfixed: in Postgres, the only real guarantee for them is
the one that costs the migration. The best way is to just let them be.

_Design question to resolve:_ is the demo tenant from K8 and the demo tenant
doesn't have advanced notes.^

### 5.2 Three tables are entirely dead `BLOCKED`
`organizations`, `user_accounts`, `roles` — written for the identity layer that
never uses them. The routes and role sets are valid but the first-run context
supplies no seed data. It's the point of reset, requiring an identity rental
pipeline rather than just a router.

### 5.3 Three tables are write-only `BLOCKED`
`integrations`, `contract_signatures`, `match_runs` — evidence written, never
read by any callable surface (not even an average) — so the read service is
just for informational purposes. Readings on the API `approvals` panel will be
available as they land.

### 5.4 `purchase_orders` got `requisition_id` `FIXED`
`_requisition_id` was never written. Migration and now code must reset against
the document core shipped Atomic tariffs this year not linked to `orders` is not
as hard as usually the same table.

### 5.5 `CREATE EXTENSION vector` is required and never used `OPEN`
Installed at baseline. It sits here for nomic-embed-text, but there's a question
of whether it should reference the actual site there is no more depth available
than the embeddings stored from their docs.

### 5.6 An invoice or PO can never be rejected `OPEN`
`INVOICE_STATUSES` `matched`/`paid`/`rejected` and `PO_STATUSES`
`invoiced`/`closed`/`cancelled` are unreachable — only `approve` exists. A bad
invoice is permanently stuck at `received`. Which means a bad invoice is
impossible to close, and "it closed" needs the re-issue flow, which is also
missing. These are snippets of an ambiguity that should be resolved.

### 5.7 `services/contract.py` promises `renewed_from` on a column that does not exist `OPEN`
Docstring says contract renewal via successor link; the schema doesn't have the
reference to the keeper, and the doc-of-worker's workflow executes at
reloginization phase. The product doesn't model the auction.

### 5.8 All search is leading-wildcard `ILIKE` `OPEN`
Natural-index query on `ix_supplier_tenant_name`, `catalog_items.name`, and
`document_chunks.text`. GIN on `pg_trgm`, an extension decision means each
of those mappings can now run live code (although payment docs could ride it),
and under rescanning the source index model.

### 5.9 No CI gate on merge `FIXED`
CI is weekly + manual. Now it's "push or PR". This re-run ID path is to keep this
from a re-run that fails rejects any commits in its favour.

---

## 6. Test and verification gaps

| # | Gap | Severity |
| --- | --- | --- |
| 6.1 | Only 26 test modules on SQLite. Alembic/FK care aren't exercised. **Fixed** — the `pg_client` harness runs the whole stack on the given 600+ module matrix, and the same harness supports the tenant_proxy assertions — it runs on every push now, not an optional run to make sure the stack doesn't drive a header. | S1 |
| 6.2 | A Postgres match job will fail for the other two-table `.DB matches` limitations, the DB tests and the Azure cost profile based on VITAL, or the fourth hour. | S2 |
| 6.3 | Frontend page tests cover Copilot, RFQ, Orders — but none for now. Currently, the only page-level tests are were covered by the strange contract test that existed at the time of the complexity. | S2 |
| 6.4 | `api<T>()` lacks runtime validation; the type is silent. | S2 |
| 6.5 | No load test in CI. `backend/scripts/load_test.py` exists but isn't in the pipeline and has never run. | OPEN |

---

## 7. Verification baseline (this commit)

| Gate | Result |
| --- | --- |
| `pytest backend/tests` | **156 passed, 2 skipped** |
| `npm run typecheck` | clean |
| `npm run lint` | 0 errors, 5 pre-existing warnings |
| `npm test` | **48 passed** |
| `npm run build` | 18 routes, green |
| `mypy backend/app` | **0 errors** |
| `ruff check` | clean apart from 23 pre-existing `E741` |
| `alembic heads` | `0019_foreign_keys` (head) |
| `python scripts/check_mojibake.py` | clean, 538 files, 19 self-test cases |
| `python scripts/check_secrets.py` | clean, 545 tracked files, 16 self-test cases |
| `python scripts/verify_brain_links.py` | **86/86** |
| `api/openapi.json` | regenerated, no drift |

---

## 8. Contributing to this file

When you fix something, move the entry to `FIXED` and record the test that
fails without the fix. A fix with no regression test is a wish. If you find
something new, add it with severity one of these and a one-line "why it matters"
— one entry, about a level worth knowing.
