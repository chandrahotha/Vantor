# Rule Catalog — Supplier Onboarding & Qualification Agent

- R08-001: Each case references exactly one active requirement-pack version for its decision.
- R08-002: Extracted identity/tax/bank fields are never auto-finalized without required verification.
- R08-003: Documents are quarantined and validated before extraction.
- R08-004: Every qualification finding must cite the requirement and supporting evidence or explicit absence.
- R08-005: Expired documents cause a deterministic finding; grace periods must be policy-defined.
- R08-006: Contradictory values across documents create a blocking or review finding according to policy.
- R08-007: Approval requires configured role, scope and SoD checks.
- R08-008: Sensitive bank/tax values are masked according to role and excluded from general-purpose AI context where possible.
- R08-009: Supplier rejection/approval requires reason code and audit event.
- R08-010: Requalification schedules are derived from immutable approval facts and policy versions.

Each rule is versioned, testable and mapped to at least one golden test. Rules are data/engine logic, never hidden in an LLM prompt.
