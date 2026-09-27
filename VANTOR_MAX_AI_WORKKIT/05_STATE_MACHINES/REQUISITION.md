# Requisition State Machine

Draft -> Submitted -> Approved OR Rejected -> Ordered.

Rules: only Draft is editable; submit creates required approval tiers atomically; Ordered requires a linked PO; rejected requires reason; no direct status mutation.

Every transition requires an explicit command, preconditions, actor authority, audit event and concurrency rule.
