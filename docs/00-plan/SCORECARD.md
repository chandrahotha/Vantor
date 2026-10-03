<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Scorecard — VANTOR

**Rewritten 2026-10-02.** The two previous drafts of this file were concatenated together with
heavily corrupted prose in large stretches of the first draft (garbled mid-sentence text, a stray
non-English token, duplicate section numbering) and were, independently of the corruption, stale:
both asserted "RLS is on all 40 tables" as an unqualified strength with no caveat, when in fact
every RLS policy in the schema was a complete no-op for the application's own database connection
until [`RE_AUDIT_2026-10-02.md`](audit-findings/RE_AUDIT_2026-10-02.md) (finding RA-001) fixed it
this session. A wrong claim is worse than a missing one, so this file is now short and defers to
that audit for anything substantive rather than re-asserting scores that aged out from under it.

For the current, evidence-backed state of the system — area-by-area completion percentages, the
release-blocker matrix, and the release decision — see
[`RE_AUDIT_2026-10-02.md`](audit-findings/RE_AUDIT_2026-10-02.md). That document is the live source
of truth. This one exists only to record what a point-in-time qualitative read is worth noting
that the audit's quantitative findings don't fully capture.

## What's genuinely good, independent of any single number

- Money is integer minor units everywhere; nothing sums across currencies without an explicit,
  tested refusal to do so.
- The audit hash chain is a real hash chain with a documented, tested fix for its one historical
  ordering bug, and `verify_chain` actually walks `prev_hash → hash` links rather than trusting
  timestamp order.
- The AI gateway is honest by construction: `disabled` is the default, no provider is ever
  silently substituted, and the one mutating tool is deliberately unreachable from the model.
- Refusal error codes are specific (`BUDGET_EXCEEDED`, `PRICE_THIN_HISTORY`, etc.) rather than
  generic — this is a real product-quality signal, not padding.
- The existing bug register's own convention — every fix ships with the regression test that
  fails without it — is sound and was followed for every fix in this session's audit too.

## What this file will not do

Restate a 1-10 score per dimension. The previous drafts' scores are exactly the kind of claim this
repository's own audit discipline (`docs/00-plan/audit-findings/`) exists to stop trusting at face
value — read the linked audit's evidence instead of a number here.
