# Outbox Architecture

Every external event is written to an outbox row in the same DB transaction as the business change. A worker claims outbox rows, publishes/delivers, and marks completion/retry state. Exactly-once external delivery cannot be assumed; make consumers idempotent.
