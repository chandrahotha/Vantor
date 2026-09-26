# Portfolio Definition of Done

A product is not complete when the UI renders. It is complete only when all of these are true:

- local setup works from a clean clone
- migrations apply and rollback strategy is documented
- synthetic seed is deterministic and clearly marked
- all material domain writes are authorized
- tenant isolation and object authorization pass adversarial tests
- audit events are append-only and verifiable
- deterministic calculations have golden vectors and reproducible run hashes
- AI outputs have schemas, evidence constraints and run records
- async jobs are idempotent and recoverable
- every primary screen has loading/empty/error/denied/stale states
- exports include evidence/provenance where appropriate
- security and dependency gates pass
- demo mode cannot contact real external supplier/ERP systems
- deployment and disaster-recovery procedures are documented
- product contract is versioned and compatible with portfolio integrations
- release checklist is signed off
