# Open Questions

These are decisions the implementation agent must not invent if they materially alter business policy:

1. Exact approval authority matrix by role/value/resource.
2. Supported tenant currencies and FX provider/source of truth.
3. Target production regions and data residency requirements.
4. Tax/e-invoicing rules by target jurisdiction.
5. Object-storage vendor/region and retention policy.
6. AI provider/data-sharing policy and allowed models.
7. Payment-state source of truth: internal status vs ERP/payment adapter.
8. Contract e-sign provider(s) and webhook protocol.
9. Target scale: tenants, users, documents, invoices and API throughput.
10. Required RPO/RTO and disaster-recovery geography.

Where these are undefined, implement a configurable policy layer rather than hardcoding an assumption.
