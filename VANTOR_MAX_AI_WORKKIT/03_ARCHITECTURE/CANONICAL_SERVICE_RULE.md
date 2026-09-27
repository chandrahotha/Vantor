# Canonical Service Rule

When two code paths enforce the same rule, one must become canonical. VNT-001 and VNT-013 demonstrate the danger of keeping `matching.py` and `purchase.py` as independently evolving matchers.

Create canonical services for:

- approval authorization;
- state transitions;
- invoice matching;
- budget reservation;
- document ingestion;
- webhook dispatch;
- audit event construction.

Routes should call these services rather than reproduce logic.
