# Test Plan — Procurement Spend Intelligence Agent

## Test layers
1. Pure unit tests for deterministic business logic.
2. Golden vector tests for calculations.
3. Property-based tests for invariants.
4. Repository/integration tests with PostgreSQL/Redis/object storage.
5. API contract tests.
6. Browser E2E tests for every primary happy path.
7. Security regression suites.
8. Failure-recovery tests.
9. Performance tests for expensive analytical paths.
10. Cross-product contract tests.

## Required invariants
- no cross-tenant visibility
- no unauthorized state transition
- repeat of an idempotent command produces the same durable result
- deterministic engine replay produces identical result hash from identical frozen inputs
- export contains the same decision facts as the approved source snapshot
- AI outage does not corrupt deterministic results
- evidence references remain valid after reruns
