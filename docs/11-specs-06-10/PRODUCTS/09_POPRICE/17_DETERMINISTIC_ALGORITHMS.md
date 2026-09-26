# Deterministic Algorithms — PO Price Intelligence Engine

1. Ingest PO lines. 2. Normalize commercial basis. 3. Generate peer candidates. 4. Evaluate comparability reasons. 5. Build frozen baseline from eligible peers. 6. Calculate variance and thresholds. 7. Decompose leakage. 8. Create anomaly or clear result. 9. Present evidence and confidence. 10. Route exceptions and optionally create ProcurementOS/CostPilot work.

## Invariants
- Same frozen input snapshot + same policy + same engine version = same deterministic result.
- All numerical transformations record their basis.
- Invalid input yields a controlled state, never a guessed number.
