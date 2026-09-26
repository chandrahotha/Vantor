# Rule Catalog — PO Price Intelligence Engine

- R09-001: Comparability is evaluated before anomaly detection.
- R09-002: Allowed states are COMPARABLE, PARTIAL and NOT_COMPARABLE; reasons are mandatory for PARTIAL/NOT_COMPARABLE.
- R09-003: Currency conversion is frozen at run time and preserves source amount/currency.
- R09-004: UOM conversion requires versioned conversion basis.
- R09-005: Taxes are not mixed into net-of-tax benchmarks unless policy explicitly defines the comparison basis.
- R09-006: Freight, discount and other commercial components must be included/excluded consistently across the peer set.
- R09-007: Stale or thin history produces a documented confidence reduction or blocks a definitive exception.
- R09-008: Thresholds are versioned and can be category/supplier-specific where policy permits.
- R09-009: Dismissals require a reason and remain auditable.
- R09-010: Leakage amount is a deterministic decomposition, never an AI-generated estimate.

Each rule is versioned, testable and mapped to at least one golden test. Rules are data/engine logic, never hidden in an LLM prompt.
