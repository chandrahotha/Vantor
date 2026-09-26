# Rule Catalog — Strategic Sourcing Optimization Engine

- R06-001: Every requirement quantity must have a valid UOM and a normalized value before solving.
- R06-002: Currency normalization uses a frozen FX snapshot; no live FX calls during deterministic solve.
- R06-003: Eligibility is a hard precondition; ineligible suppliers cannot receive allocation.
- R06-004: Minimum order quantity and increment constraints are enforced at line and supplier-period scope.
- R06-005: Supplier capacity is time-phased; stale capacity may block a definitive solve depending on policy.
- R06-006: Risk/dependency limits are expressed as constraints or objective penalties with explicit policy version.
- R06-007: Soft-constraint relaxation must list which constraint relaxed, magnitude and policy permission.
- R06-008: Post-solver validation independently recomputes demand coverage, capacity, MOQ, policy and financial totals.
- R06-009: Infeasible results never become allocation recommendations.
- R06-010: Identical frozen inputs + policy + engine version must yield the same normalized model hash and solution hash.

Each rule is versioned, testable and mapped to at least one golden test. Rules are data/engine logic, never hidden in an LLM prompt.
