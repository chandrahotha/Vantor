# Deterministic Algorithms — Supplier Onboarding & Qualification Agent

1. Create case and select requirement pack. 2. Receive and quarantine documents. 3. Validate type/signature/size/malware. 4. Extract fields and evidence. 5. Normalize and compare fields across documents. 6. Evaluate checklist rules and expiry. 7. Route missing/contradictory findings. 8. Human corrects/confirm fields. 9. Reviewer evaluates checklist. 10. Approval gate publishes supplier snapshot and schedules requalification.

## Invariants
- Same frozen input snapshot + same policy + same engine version = same deterministic result.
- All numerical transformations record their basis.
- Invalid input yields a controlled state, never a guessed number.
