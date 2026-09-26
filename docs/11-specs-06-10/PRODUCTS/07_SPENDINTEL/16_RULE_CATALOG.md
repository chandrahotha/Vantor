# Rule Catalog — Procurement Spend Intelligence Agent

- R07-001: A source transaction is immutable; corrections create a superseding normalized version.
- R07-002: Published spend cube totals reconcile to accepted transaction values within documented rounding policy.
- R07-003: Classification below confidence threshold enters review; it cannot be silently published.
- R07-004: Supplier/entity aliases are tenant-scoped and source-traceable.
- R07-005: Taxonomy versions are immutable; reclassification creates a new snapshot rather than rewriting history.
- R07-006: Savings claims require explicit baseline, target basis, time horizon and exclusion rules.
- R07-007: Maverick spend is rule-derived from approved policy, contract and transaction facts.
- R07-008: Concentration metrics declare denominator, period, currency basis and supplier grouping logic.
- R07-009: AI may rank review work but cannot override deterministic reconciliation or publication controls.
- R07-010: Every executive metric can drill to the underlying snapshot and source transaction set.

Each rule is versioned, testable and mapped to at least one golden test. Rules are data/engine logic, never hidden in an LLM prompt.
