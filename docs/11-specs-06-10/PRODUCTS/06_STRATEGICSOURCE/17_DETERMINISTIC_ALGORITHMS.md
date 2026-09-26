# Deterministic Algorithms — Strategic Sourcing Optimization Engine

1. Build frozen input snapshot. 2. Normalize money/quantity/UOM. 3. Filter eligible suppliers. 4. Construct variables x[supplier,item,period]. 5. Add demand, capacity, MOQ/lot, supplier-count, geography, risk and business-policy constraints. 6. Define deterministic objective from weighted cost/risk/delivery dimensions. 7. Solve with deterministic configuration. 8. Independently validate solution. 9. Compute allocation, objective and policy metrics. 10. Hash canonical inputs/model/solution. 11. Emit result and, only if policy allows, queue approval.

## Invariants
- Same frozen input snapshot + same policy + same engine version = same deterministic result.
- All numerical transformations record their basis.
- Invalid input yields a controlled state, never a guessed number.
