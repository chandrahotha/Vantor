# Acceptance Criteria — Supplier Onboarding & Qualification Agent

## Product-level acceptance

- [ ] All 11 phases pass their exit gates.
- [ ] Core workflows work from clean synthetic seed.
- [ ] All primary screens `O01 Onboarding Queue, O02 Supplier Invitation, O03 Registration Workspace, O04 Document Intake, O05 Evidence Viewer, O06 Data Extraction Review, O07 Qualification Checklist, O08 Risk & Compliance, O09 Missing Information, O10 Reviewer Workspace, O11 Approval, O12 Supplier Profile, O13 Requalification Calendar, O14 Audit Trail, O15 AI Activity, O16 Export` are implemented.
- [ ] RBAC/object authorization and tenant isolation are adversarially tested.
- [ ] Deterministic engine golden vectors are green.
- [ ] AI functions have explicit schemas and outage fallback.
- [ ] Material actions are approval-gated.
- [ ] Audit trail is append-only and verifiable.
- [ ] API contract is versioned.
- [ ] Cross-product contract tests pass.
- [ ] CI release gate is reproducible.
