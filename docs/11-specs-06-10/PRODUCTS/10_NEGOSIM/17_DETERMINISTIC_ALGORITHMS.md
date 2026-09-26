# Deterministic Algorithms — AI Supplier Negotiation Simulator

1. Compile read-only evidence pack. 2. Set buyer objectives and hard guardrails. 3. Select bounded supplier persona. 4. Initialize deterministic offer ledger. 5. Send constrained LLM turn request. 6. Validate output against schema and policy. 7. Apply deterministic offer/concession arithmetic. 8. Store round. 9. Continue/branch/pressure-test. 10. Run deterministic score rubric. 11. Generate clearly labeled coaching/debrief. 12. Export simulation artifact with evidence and model metadata.

## Invariants
- Same frozen input snapshot + same policy + same engine version = same deterministic result.
- All numerical transformations record their basis.
- Invalid input yields a controlled state, never a guessed number.
