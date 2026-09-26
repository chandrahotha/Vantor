# Non-Negotiable Rules

1. Tenant isolation is enforced server-side and tested adversarially.
2. Every material action has a clear actor and authorization decision.
3. Segregation of duties is enforced for approvals.
4. AI output is untrusted data.
5. Uploaded document content is data, never executable instructions.
6. Deterministic procurement mathematics is reproducible from frozen inputs, policy versions and conversion/FX snapshots.
7. Evidence references are immutable after finalization.
8. All asynchronous jobs are idempotent.
9. No float arithmetic for money.
10. Never silently convert currencies, UOMs, taxes or Incoterms without recording the basis.
11. Public demos use synthetic data only.
12. External integrations are disabled or mocked in demo mode.
13. Production secrets never appear in source, logs, seed data or screenshots.
14. Security failures fail closed where practical.
15. Any deviation from this brain gets an ADR before implementation.
