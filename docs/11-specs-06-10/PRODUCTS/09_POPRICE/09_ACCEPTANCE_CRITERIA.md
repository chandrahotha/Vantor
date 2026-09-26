# Acceptance Criteria — PO Price Intelligence Engine

## Product-level acceptance

- [ ] All 11 phases pass their exit gates.
- [ ] Core workflows work from clean synthetic seed.
- [ ] All primary screens `P01 Price Control Tower, P02 PO Intake, P03 PO Line Detail, P04 Comparability Review, P05 Price History, P06 Benchmark Builder, P07 Anomaly Analysis, P08 Leakage Breakdown, P09 Contract Check, P10 Review Queue, P11 Investigation Workspace, P12 Resolution, P13 Reports, P14 Export, P15 Rules & Thresholds, P16 Run History` are implemented.
- [ ] RBAC/object authorization and tenant isolation are adversarially tested.
- [ ] Deterministic engine golden vectors are green.
- [ ] AI functions have explicit schemas and outage fallback.
- [ ] Material actions are approval-gated.
- [ ] Audit trail is append-only and verifiable.
- [ ] API contract is versioned.
- [ ] Cross-product contract tests pass.
- [ ] CI release gate is reproducible.
