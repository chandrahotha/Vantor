# Transaction Model

Every financial command must specify:

1. rows read;
2. rows locked;
3. invariants checked under lock;
4. rows written;
5. ledger/audit records created;
6. external effects deferred until commit;
7. retry/idempotency behavior.

Prefer `SELECT ... FOR UPDATE` on a deterministic set of aggregate rows or an atomic conditional mutation. For multi-row locks, sort IDs before locking to reduce deadlock probability.
