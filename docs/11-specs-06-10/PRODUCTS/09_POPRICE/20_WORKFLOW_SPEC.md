# Workflow Specification — PO Price Intelligence Engine

## State machine
`new → normalizing → comparable → analyzed → exception / clear → accepted / dismissed → closed`

## Transition contract
Every transition must define:
- current state
- allowed actor roles
- preconditions
- side effects
- emitted event
- audit event
- idempotency semantics
- failure/rollback behavior

## Concurrency
Use optimistic concurrency or transaction locking for competing decisions. A stale client must receive `CONFLICT` rather than silently overwrite a newer state.

## Materiality
Approvals are triggered by policy, not by UI convention. UI cannot bypass a server-side material-action check.
