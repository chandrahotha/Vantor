<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Bug & Risk Register — VANTOR

**Rewritten 2026-10-02.** The previous version of this file had large stretches of genuinely
corrupted prose — garbled mid-sentence text, stray tokens, sentences that stopped making sense
partway through (e.g. "twoconcurrent evaluations", "zoomedynical scope", "rejects any commits in
its favour") — scattered through roughly a third of its bug entries. Reconstructing the exact
original wording of a corrupted sentence from context is guessing, and a guessed claim is exactly
the kind of thing this register exists to prevent. Rather than guess, this rewrite keeps only what
was verifiably clean in the old file, plus everything independently re-verified against current
source during [`RE_AUDIT_2026-10-02.md`](audit-findings/RE_AUDIT_2026-10-02.md) (which also
re-checked the 45-item [`MASTER_FINDINGS.md`](audit-findings/MASTER_FINDINGS.md) register). For
anything not listed below from the old file, treat it as unverified until re-derived from source
or tests — slow but sound, per this file's own long-standing rule (§4).

**For current, substantive findings, read `RE_AUDIT_2026-10-02.md`, not this file.** This register
is being kept as the living day-to-day bug log going forward; the audit document is the point-in-time
evidence record.

## 1. How to read the status column

| Status | Meaning |
| --- | --- |
| `FIXED` | Repair + regression test so it can't slide back in |
| `FIXED (untested)` | Fixed, but a test is still pending — claim by claim doesn't do it |
| `OPEN` | Known, unfixed and not scheduled |
| `BLOCKED` | Cannot be fixed safely without a decision or a data pass |

Severity is about consequence, not effort: **S1** corrupts money, leaks a tenant, or silently
disables a control. **S2** produces a wrong answer or strands a user. **S3** degrades performance,
ergonomics, clarity.

## 2. Current S1-level findings (from `RE_AUDIT_2026-10-02.md`)

| ID | Finding | Status |
| --- | --- | --- |
| RA-001 | Every RLS `tenant_isolation` policy was a no-op for the application's own database connection (it connected as a Postgres superuser, which Postgres never subjects to row security) | `FIXED` — restricted `vantor_app` role (migration `0026`), live-reproduced before and after, new regression test proves cross-tenant denial through the real HTTP/app layer |
| RA-002 | `docker compose up` never ran database migrations anywhere in the stack; the documented multi-tenant deployment path 500'd on every real endpoint from a clean database | `FIXED` — one-shot `migrate` service gates `backend` startup, live-reproduced before and after |
| RA-003 | A `db.commit()` + `db.refresh(row)` pattern across routers broke once RLS actually applied (RA-001 exposed this; it was invisible before) | `FIXED` — tenant pin now re-applied automatically on every transaction a session opens via a `Session`-level event listener |

Full evidence, file:line citations, and verification commands for all of the above are in
`RE_AUDIT_2026-10-02.md` §1.

## 3. Historical fixes confirmed still in place (re-verified 2026-10-02, not re-describing the original defect)

The following fixes from the prior register were independently re-verified against current source
and still hold, each with a named regression test:

- Idempotency key width / fingerprint hashing — `backend/alembic/versions/0016_idempotency_key_width.py`, `test_idempotency_search.py`
- AI provider key resolution (request > env > fail-named) — `backend/app/services/ai_gateway.py`, `test_ai.py`
- Partial invoicing / duplicate-billing detection — `backend/app/services/purchase.py` (`three_way_match`), `test_matching.py`
- Award savings computed from a pre-flip baseline — `backend/app/routers/sourcing.py`, `test_sourcing.py::test_award_records_real_savings`
- Approval tiers cleared in defined order, not row order — `backend/app/routers/purchase.py` (`order_pending`), `test_approvals.py`
- HITL approval lifecycle has a real decide path — `GET /approvals`, `POST /approvals/{id}/decide`, `test_approvals.py`
- Quarantined documents excluded from search — `backend/app/routers/documents.py`, `test_idempotency_search.py`
- Webhook duplicate delivery collapses to `skipped_duplicate`; slow webhooks hit a deadline, not a 20s request-wide stall — `backend/app/services/integration.py`, `test_integrations.py`
- AI gateway SSRF protections on webhook URLs (DNS-rebind-at-dial-time, redirect refusal, cloud-metadata-IP blocking) — `backend/app/services/egress.py`, `test_integrations.py`
- Zip-bomb / archive-bomb resource limits on DOCX/XLSX extraction — `backend/app/services/extract.py`, `test_extract.py`
- Copilot duplicate React keys fixed, BYOK key-entry flow added — `frontend/app/copilot/page.tsx`, `turns.test.tsx`, `byok.test.tsx`
- Mixed-currency spend totals refused rather than silently summed — `backend/app/services/spend.py`, `test_spend_intel.py`

## 4. Known open items (confirmed still open 2026-10-02)

- Broadcast notification unread count remains an approximate, capped scan rather than an exact
  count (by design, surfaced honestly via `unreadCapped: true`) — `backend/app/routers/notifications.py`.
- `23 ruff E741` style warnings — pre-existing, deliberately not fixed (churn without payoff).
- Document semantic search still does an ILIKE prefilter + Python-side cosine ranking rather than
  a DB-side `<=>` query against the real pgvector/HNSW index that already exists — see
  `RE_AUDIT_2026-10-02.md` RA-006.
- `contracts.status`, `contract_obligations.status`, `documents.status` still lack DB-level CHECK
  constraints that most other status enums in the schema already have — see RA-008.
- `should_cost.py`'s `gap_vs_quote` silently returns `variance_bp: 0` on a non-positive baseline
  instead of raising, unlike the equivalent check in `price_intel.py` — see RA-007.
- AI grounding checks evidence *presence*, not evidence *fidelity* against the generated answer —
  see RA-005.
- `scripts/doc_counts.py`'s CI job doesn't install dependencies, so the anti-drift gate it exists
  to provide silently reports `None` instead of catching drift — see RA-009.
- Frontend E2E/accessibility/visual-regression suite has not demonstrably passed in CI (a
  `backend/data/` directory-creation ordering issue) — see RA-010.

## 5. Contributing to this file

When you fix something, add it to §2 with status `FIXED` and name the regression test that fails
without the fix — a fix with no regression test is a wish, not a fix. If you find something new,
add it to §4 with severity and a one-line "why it matters." Do not reconstruct a status for
something you haven't personally re-verified against source or a passing test; an honest "unknown,
re-check" beats a plausible-sounding guess every time, which is the whole reason this file needed
rewriting in the first place.
