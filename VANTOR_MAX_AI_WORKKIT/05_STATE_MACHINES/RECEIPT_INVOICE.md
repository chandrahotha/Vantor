# Receipt and Invoice State Machine

Receipt is append-only; each line is cumulative against ordered quantity. Invoice: Received -> Matched -> Approved -> Paid, with Rejected/Hold paths. Matching is a prerequisite, not the approval itself.

Every transition requires an explicit command, preconditions, actor authority, audit event and concurrency rule.
