# Business Rules Catalog

| Rule ID | Rule | Enforcement | Tests |
|---|---|---|---|
| BR-P2P-001 | Invoice cumulative quantity cannot exceed received quantity per PO line. | DB transaction + canonical matcher | Unit/integration/concurrency |
| BR-P2P-002 | Received quantity cannot exceed ordered quantity. | Locked receipt transaction | Unit/concurrency |
| BR-P2P-003 | Actual spend must be unique per approved invoice. | DB unique key + state command | Concurrency/retry |
| BR-P2P-004 | Commitment must be unique per sent PO. | DB unique key + state command | Concurrency/retry |
| BR-APR-001 | Requester cannot approve own request. | Shared approval service | Role matrix |
| BR-APR-002 | Approval tier sequence cannot be skipped. | Shared approval service | Tier tests |
| BR-APR-003 | Approver authority must cover the tier and value. | Policy service | Role/amount matrix |
| BR-BUD-001 | Budget reservation must be atomic. | Locked/conditional DB operation | Concurrency |
| BR-SRC-001 | Quotes compared only within one currency or normalized by audited FX. | Sourcing evaluation | Currency tests |
| BR-SRC-002 | RFQ cannot be awarded before evaluation gates pass. | State transition service | Golden journey |
| BR-CON-001 | Contract signing applies to an immutable version/snapshot. | Versioning + signature service | Version/sign tests |
| BR-DOC-001 | Uploaded bytes are immutable and content-addressed. | Object store + hash | Integrity tests |
| BR-AI-001 | Evidence-backed answers require evidence when configured. | AI policy gate | Adversarial tests |
| BR-AI-002 | AI never mutates procurement state directly. | Tool permissions + server policy | Tool abuse tests |
| BR-TEN-001 | Every read/write is tenant-scoped. | RLS + application tenant filter | Cross-tenant suite |
| BR-AUD-001 | State-changing financial actions emit an immutable audit event in same transaction. | Audit service | Rollback tests |


The coding agent must expand this catalog whenever it discovers a new invariant during implementation. No newly discovered rule may remain implicit in a router.
