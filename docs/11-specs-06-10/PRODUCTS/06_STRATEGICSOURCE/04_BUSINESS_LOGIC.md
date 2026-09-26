# Business Logic — Strategic Sourcing Optimization Engine

1. A solution is valid only if all hard constraints pass.
2. Objective weights are versioned and never altered after a run is finalized.
3. Soft constraints may be relaxed only through an explicit relaxation policy; every relaxation is reported.
4. A solution must be revalidated independently after solver output.
5. Supplier allocations must respect MOQ, capacity, award caps and eligibility.
6. Scenario comparisons use identical frozen input snapshots.
7. Infeasible problems produce a structured infeasibility explanation; never fabricate a solution.
8. Approval is required for any proposed award/allocation crossing configured materiality thresholds.
