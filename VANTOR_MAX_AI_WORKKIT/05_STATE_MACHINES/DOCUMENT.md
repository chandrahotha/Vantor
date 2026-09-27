# Document State Machine

Uploaded -> Scanning/Processing -> Ready OR Quarantined. A quarantined document cannot contribute evidence/search. Reprocessing must be idempotent and auditable.

Every transition requires an explicit command, preconditions, actor authority, audit event and concurrency rule.
