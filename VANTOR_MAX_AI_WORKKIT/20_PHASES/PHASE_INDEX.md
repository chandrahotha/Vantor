<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Autonomous Build Phase Index

- **Phase 00: BASELINE** — Re-read repo; verify baseline/tests; create issue map; no feature changes.
- **Phase 01: DOMAIN AND STATE HARDENING** — Centralize state transitions, authority policy, approval flow and canonical matching.
- **Phase 02: FINANCIAL CONCURRENCY** — Fix cumulative invoice match, budget reservations, receipts, send/approve races, ledger uniqueness and idempotency.
- **Phase 03: DATABASE INTEGRITY** — Add constraints/indexes/RLS where safe; migration/repair strategy.
- **Phase 04: DOCUMENT PIPELINE** — Stream uploads, object storage, parser sandbox/resource limits, OCR/embedding pipeline.
- **Phase 05: INTEGRATIONS** — Build outbox, async delivery, retries/DLQ/replay, SSRF/egress hardening.
- **Phase 06: AI SAFETY** — Evidence contract, immutable prompt policy, tool permissions, evaluation suite and provider governance.
- **Phase 07: API AND SECURITY** — API errors, pagination, rate limits, headers, async I/O, tenant/RBAC hardening.
- **Phase 08: GRADE-5 DESIGN SYSTEM** — Build reusable component system and app shell.
- **Phase 09: SCREEN REBUILD** — Rebuild all operational screens and add first-class Approval/Invoice/Health/Admin surfaces.
- **Phase 10: PERFORMANCE AND SRE** — Remove blocking paths, optimize DB/search, implement telemetry/SLOs/alerts.
- **Phase 11: PRODUCTION DEPLOYMENT** — Harden containers, Keycloak, secrets, network, migrations, backups, rollback.
- **Phase 12: FINAL ADVERSARIAL AUDIT** — Re-scan full repo for old patterns, run complete CI, compare docs to code.

The phase prompts are dependency-ordered. The agent may add sub-phases when evidence requires them, but cannot skip a release gate.
