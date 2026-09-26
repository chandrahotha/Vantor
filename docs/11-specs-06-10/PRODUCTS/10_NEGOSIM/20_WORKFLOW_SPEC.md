# Workflow Specification — AI Supplier Negotiation Simulator

## State machine
`draft → prepared → running → paused → completed / aborted → debriefed → archived`

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
