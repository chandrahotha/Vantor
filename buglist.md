<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# Bug list — final ledger

**This file is temporary and is deleted as part of signing off.** It exists so the
audit has one place recording what was found, what was fixed, how it was verified,
and what is still owed. Do not link to it from durable documentation.

Source of truth for the findings is
[`VANTOR_MAX_AI_WORKKIT/02_FINDINGS/MASTER_FINDINGS.md`](VANTOR_MAX_AI_WORKKIT/02_FINDINGS/MASTER_FINDINGS.md)
(45 findings, VNT-001 … VNT-045).

## Final verification

| Gate | Result |
|---|---|
| Backend suite | **296 passed, 2 skipped** (298 collected) |
| Frontend suite | **99 passed**, 9 files |
| `ruff check app tests alembic` | clean |
| `tsc --noEmit` | clean |
| `eslint` | 0 errors, 5 pre-existing warnings (4 × `<img>`, 1 × unused test var) |
| `next build` | compiled, 19 routes |
| Palette audit (WCAG AA, 5 palettes × 2 modes) | no cycles, no dangling tokens, all pairs pass |
| Migration chain | linear, 1 head, 22 migrations, both directions present |
| `check_secrets` / `check_mojibake` / `verify_brain_links` | clean |
| `doc_counts --check` | matches reality |
| `pin_digests --check` | structural pass; values need one networked run |
| `docker compose config` | parses, 11 services |

The 2 backend skips need `PG_TEST_DATABASE_URL`. There is no PostgreSQL reachable
from this environment and no Docker engine installed, so the PostgreSQL tier could
not be run. That is recorded as owed, not as passing.

## Findings

| ID | Status | Note |
|---|---|---|
| VNT-001 | Fixed | Cumulative *approved* quantity, inside the locked transaction. |
| VNT-002 | Fixed | PO approval requires `APPROVER_ROLES`. |
| VNT-003 | Fixed | Invoice approval requires `APPROVER_ROLES`. |
| VNT-004 | Fixed | Budget row locked before the aggregate read. |
| VNT-005 | Fixed | Receipt locks the PO and checks cumulative quantity. |
| VNT-006 | Fixed | Atomic claim; the stale-claim takeover is a real compare-and-swap `UPDATE`. |
| VNT-007 | Fixed | Layered SSRF policy, **and the connection is actually pinned** to the validated address. |
| VNT-008 | Fixed | Durable outbox, retry/backoff, dead-letter, replay. |
| VNT-009 | Fixed | Pluggable storage driver, tenant-scoped keys, volume on the backend. |
| VNT-010 | Fixed | Streamed ingest with a hard cap. |
| VNT-011 | Fixed | Archive limits. The zip-bomb concern was investigated and **refuted** — see R-2. |
| VNT-012 | Fixed | Full magic/MIME/extension cross-check. |
| VNT-013 | Fixed | Attachment targets validated against tenant-owned models. |
| VNT-014 | Fixed | Ungrounded completions refuse. |
| VNT-015 | Fixed | House policy non-overridable; caller input fenced. |
| VNT-016 | Fixed (PG unverified) | `vector(n)` column, HNSW index, dimension validation, migration 0022. DDL asserted structurally, not executed. |
| VNT-017 | Fixed | Exact below the cap, approximation reported above it. |
| VNT-018 | Fixed | Lifecycle endpoints; `matched` now has a writer and every transition is checked. |
| VNT-019 | Fixed | RFQ locked; duplicate award is a 409. |
| VNT-020 | Fixed | Eligibility, line mapping, evaluation completeness. |
| VNT-021 | Fixed | Quote currency must match the RFQ. |
| VNT-022 | Fixed | Per-action authority; refusals name the action and the roles. |
| VNT-023 | Fixed | HMAC-verified provider callback + `verified_via` provenance (migration 0021). |
| VNT-024 | Partial | Roll is `Super Admin`-only, tenant-scoped and clock-injectable. Still: the worker's service account holds `Super Admin` to call it, and "today" is one global timezone rather than per-tenant. |
| VNT-025 | Fixed | `VERIFY_CERT_ROLES`; evidence and expiry required. |
| VNT-026 | Fixed | `DECIDE_QUAL_ROLES` restricted to compliance. |
| VNT-027 | Fixed | Unique ledger key; duplicate post is a 409. |
| VNT-028 | Fixed | ~30 CHECKs and the business-key uniques, in migrations 0020–0022, with a drift test. |
| VNT-029 | Fixed | Cold JWKS fetch off the loop; warm path inline deliberately. |
| VNT-030 | Fixed | Request IDs constrained to a safe character set. |
| VNT-031 | Partial | CSP and the security headers are on API responses. The Next.js app's own responses do not consume a nonce. |
| VNT-032 | Fixed | Tenant in the key; validated fail mode; unauthenticated requests are now counted. |
| VNT-033 | Fixed | Per-route series, p50/p95/p99, business counters, valid exposition format, delivery correlation id. |
| VNT-034 | Fixed | No host-published infrastructure; Redis passworded; non-root, read-only, capability-dropped, limited. |
| VNT-035 | Fixed | Digest pinning with an offline structural gate. Digests need one networked run to populate `.env`. |
| VNT-036 | Fixed | Idempotent realm provisioning over the admin API; no secret in the committed realm. |
| VNT-037 | Fixed | Unique turn ids. A second question was overwriting the first answer. |
| VNT-038 | Fixed | BYOK entry flow; the backend already supported the key. |
| VNT-039 | Partial | Token system, contrast audit, and the switcher's semantics fixed. The four `<img>` performance warnings remain by choice. |
| VNT-040 | Partial | Backend lint, migration-chain audit, palette audit, nav-coverage test, and 60+ new tests are now CI gates. **No real browser E2E, visual regression, a11y automation or load gate** — no browser in this environment. |
| VNT-041 | Fixed | Expiry window calculated live; the count is no longer a 5-row sample. |
| VNT-042 | Fixed | Counts derived and gated. Three READMEs had contradicted each other. |
| VNT-043 | Fixed | A cross-currency total is now `null` rather than a wrong number. |
| VNT-044 | Fixed | The worker does its own client-credentials grant. |
| VNT-045 | Fixed | The approval queue has a route and a nav entry, with a coverage test. |

## Defects found while fixing the above

Not in the register. Each was found by reading or testing the fix, and each has a
regression test.

| # | Severity | Note |
|---|---|---|
| D-1 | **Critical** | Migration 0020 called `_preflight()` before creating the columns it queried, and reported statuses its own backfill was about to fix. It could not run against a populated database. Order is now add → backfill → preflight → constrain. |
| D-2 | **High** | `uq_sig_tenant_provider_envelope` was a plain unique constraint over columns that are `NOT NULL` with a `""` default, so every internal signature shared `(tenant, '', '')` and the **second internal signature in a tenant was rejected by the database**. Now a partial unique index on e-sign rows. |
| D-3 | **High** | SSRF protection computed the pinned address, discarded it, and posted to the hostname — the rebinding window the comment claimed to have closed was open. Now pinned, with the hostname preserved in `Host` and the TLS SNI. |
| D-4 | **High** | The idempotency stale-claim takeover built an `INSERT` with a `.where()`, so it always raised into a fail-open. The endpoint appeared to recover while the row stayed `in_progress` forever. |
| D-5 | Medium | `INVOICE_FLOW` was a declaration compared against another declaration; its `matched` state had no writer. |
| D-6 | Medium | `deploy/keycloak/init.sh` (first draft) connected to `localhost` for another container's database. Replaced by the admin-API approach. |
| D-7 | Medium | The first compose draft mounted `uploads-data` on `frontend`. Nothing writes documents there. Moved to the backend. |
| D-8 | Low | The realm template had a duplicate JSON key and a `serviceAccountClientRoles` block no code read. |
| D-9 | Medium | The `--primary: var(--primary)` self-reference I introduced in the token bridge. Invalid at computed-value time, so the property silently inherited its root default and every button would have stayed blue under all five palettes. |
| D-10 | Medium | The palette preference never persisted: `layout.tsx` server-renders `data-palette="graphite"` and my `readDom() ?? readStorage()` ordering meant the stored choice always lost. |
| D-11 | High | `egress.validate_url` read `port` before assigning it, so registering a webhook against a **public IP literal** raised `NameError`. Found by ruff; no test covered the branch because they all used hostnames. |
| D-12 | **High** | `ai_gateway.stream` took no `grounding`, so `/ai/stream` — the path the copilot uses — answered *without* the tool results the response then cited, shipping evidence chips and a confidence number for evidence the model never saw. |
| D-13 | Medium | `/ops/metrics.prom` emitted `metric {label="v"} 0`. The exposition format forbids whitespace before the label set, so Prometheus rejected the whole document — a 200 that recorded nothing. |
| D-14 | Medium | The rate limiter skipped limiting for **any** request it could not attribute, so unauthenticated floods were unbounded and each got a free 401. |
| D-15 | Medium | The rate-limiter key omitted the tenant, so one tenant's traffic could exhaust another's allowance. |
| D-16 | Medium | `RATE_LIMIT_FAIL_MODE` was not validated; a typo ran fail-open while the config claimed otherwise. |
| D-17 | Medium | The docstring claimed a "closed for auth-adjacent paths" default that existed nowhere. |
| D-18 | Medium | Three `sqlalchemy` mistakes in the new `Vector` type, all of which failed **only** on PostgreSQL while the whole suite stayed green: `sa.UserDefinedType` does not exist, it takes no arguments, and a `TypeDecorator`'s `bind_processor` replaces the wrapped type's. |
| D-19 | Low | The vector width existed as two literals (384 and 768), so every provider vector was rejected and every chunk silently lost its embedding. |
| D-20 | Medium | My `useBoot` test mock ignored its loader, so a test suite passed against a page whose provider list never loaded. |
| D-21 | Medium | The palette cards declared `role="radio"` without implementing arrow-key navigation — semantics the component did not honour. |
| D-22 | Low | The dashboard rendered a 5-row sample as a total, and carried a note my VNT-041 change made false. |
| D-23 | Low | `test_demo_mode.py` generated a private key it never used. |

## Refuted

Recorded so these are not re-raised without new evidence.

| # | Claim | Finding |
|---|---|---|
| R-1 | `zlib` decompression is unbounded because `decompressobj.flush()` takes no length argument. | Measured. The cap is reached inside the `decompress(..., max_length)` loop and returns before `flush()` is reached; a 64 MiB bomb peaked at 2 MiB of traced allocation. |
| R-2 | `ZipFile.read()` can exceed the declared `file_size`, so the archive cap can be lied past. | Measured with a hand-patched archive declaring 1 KB for 48 MiB: `read()` stops at the declared size and then fails the CRC check. Fails closed. Now asserted by a test rather than assumed. |
| R-3 | The self-renaming of `l` in 25 comprehensions would be a safe readability fix. | Attempted and **reverted**: `l` is the generator variable, so renaming the `for` target orphans every use in the body, producing 63 undefined-name errors. Ruff runs with E741 ignored, and the reason is written down in `backend/ruff.toml`. |

## Still owed

These are not done, and none of them is claimed as passing.

- [ ] **PostgreSQL.** `alembic upgrade head`, `alembic check`, and downgrade→upgrade against a live database. Migrations 0020, 0021 and 0022 have been checked structurally and by AST/recorder, never executed by Postgres.
- [ ] **PostgreSQL concurrency tests** for the money paths: two concurrent approvals of one PO, two of one invoice, a duplicate RFQ award, an idempotency race.
- [ ] **One networked run of `scripts/pin_digests.py`** to populate `.env`. The structural gate passes; the values cannot be resolved offline.
- [ ] **`docker compose up -d --build` end to end**, including the Keycloak bootstrap and the provider callback path.
- [ ] **Real browser E2E, a11y automation, visual regression and a load gate** (VNT-040). No browser is available in this environment, so these remain assertions rather than evidence.
- [ ] **VNT-024 residue**: the worker service account holding `Super Admin`, and a per-tenant timezone rather than one global setting.
- [ ] **VNT-031 residue**: a nonce-based CSP on the Next.js responses themselves.
