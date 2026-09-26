# START HERE — LLM BUILD INSTRUCTIONS

Read files in this order:

1. `00_PORTFOLIO_BRAIN/01_MASTER_PORTFOLIO_PROMPT.md`
2. `INHERITED_TOP5_CONTRACTS/` shared contract files
3. `00_PORTFOLIO_BRAIN/02_CROSS_PRODUCT_INTEGRATION.md`
4. `00_PORTFOLIO_BRAIN/03_NON_NEGOTIABLE_RULES.md`
5. `PRODUCTS/06.../00_PRODUCT_README.md` through each product's phase plan
6. Product data model, business logic, deterministic engine, AI architecture, security, API, test plan, screens, seed data, deployment and acceptance criteria

Build each product as a standalone repository. Never collapse all five into one application.

When a requirement is ambiguous, prefer the most auditable and reversible interpretation. Record material deviations in an ADR. Never silently weaken security, evidence traceability, approvals, tenancy, or deterministic calculations.

The final system must be usable without AI availability for core deterministic workflows. AI is a capability layer, not the foundation of data integrity.
