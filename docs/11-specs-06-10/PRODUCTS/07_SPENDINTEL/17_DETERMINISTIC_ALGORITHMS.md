# Deterministic Algorithms — Procurement Spend Intelligence Agent

1. Ingest raw batch. 2. Profile schema/nulls/duplicates. 3. Normalize dates, currency and UOM where applicable. 4. Resolve supplier and item entities. 5. Map categories using deterministic rules, learned candidates and human review. 6. Publish a versioned spend cube. 7. Run maverick, concentration, price-leakage and fragmentation rules. 8. Generate opportunity baselines. 9. Assign confidence and review queues. 10. Produce evidence-backed reports.

## Invariants
- Same frozen input snapshot + same policy + same engine version = same deterministic result.
- All numerical transformations record their basis.
- Invalid input yields a controlled state, never a guessed number.
