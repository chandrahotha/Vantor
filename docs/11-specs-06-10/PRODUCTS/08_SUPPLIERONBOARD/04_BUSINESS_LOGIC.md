# Business Logic — Supplier Onboarding & Qualification Agent

1. Required qualification fields and documents come from a versioned requirement pack.
2. Missing/expired/contradictory evidence creates explicit findings.
3. Identity fields cannot be changed by extraction without user confirmation.
4. Approval cannot be performed by a disallowed actor or by the same actor where SoD forbids it.
5. Supplier status transitions are server-enforced.
6. Requalification is triggered by expiry or policy-defined events.
7. Banking/tax fields are masked in UI and logs according to role.
