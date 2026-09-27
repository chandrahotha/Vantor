<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Document State Machine

Uploaded -> Scanning/Processing -> Ready OR Quarantined. A quarantined document cannot contribute evidence/search. Reprocessing must be idempotent and auditable.

Every transition requires an explicit command, preconditions, actor authority, audit event and concurrency rule.
