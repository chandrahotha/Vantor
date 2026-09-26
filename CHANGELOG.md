<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# Changelog — VANTOR

All notable changes tracked here. Statuses: `PLANNED / IN DEVELOPMENT / IMPLEMENTED / TESTED / VERIFIED / PRODUCTION READY`.

## [Unreleased] — 2026-09-26

### Changed
- **License: Apache-2.0 → AGPL-3.0-or-later** © 2026 Digi Tracks. SaaS copyleft: modified network-service versions must publish source (§13). Commercial exceptions: digi.tracks@outlook.com.

### Added
- Procurement core: scorecards, onboarding/qualification, catalogs, budgets (hard gate on approve), e-sign records, 11-dim matching + stored runs, PO detail endpoint
- Intelligence: spend cube/leakage/maverick/concentration, should-cost engine, price baselines + anomaly cases, sourcing optimizer, negotiation simulator
- Platform: security headers + CORS, idempotency (body-bound), rate limiting, honest readiness, access logs, RQ worker, HMAC webhooks, integrations framework
- Web (Next.js 14): dashboard, suppliers grid, RFQs + comparison + pager, contracts, orders, spend intel + price cases + calculator, documents, copilot, command palette, sitemap/robots/OG
- Docs: 06–10 build-brain vendored (`docs/11-specs-06-10/`), Phase 11 planned, Android marked Coming-Soon, operations runbook implemented
- Quality: 82 pytest green, frontend typecheck + build green, 56 OpenAPI paths, brain-links 39/39, 3 QA sweeps (80+ findings fixed)

## [0.1.0] — 2026-09-25 — Docs-first scaffold [PLANNED]

### Added
- Public repo skeleton: README, LICENSE (Apache-2.0), SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, `.env.example`, `.gitignore`, `docker-compose.yml` (free stack), CI workflow
- Prerequisite docs: requirements, system/domain/database/api, AI (arch/safety/eval), security (arch/threat-model), design-system, brand/logo, android strategy, deployment, runbook, ADRs
- `docs/00-plan/REPOSITORY_AUDIT.md` (BLOCKED — awaiting private repo access), `docs/00-plan/MIGRATION_PLAN.md`, `docs/00-plan/ROADMAP.md`
- Vantor identity pack: logo/mono/dark/favicon/app-icon/social SVGs
- Module placeholders: `backend/ frontend/ worker/ android/ api/`

### Not yet implemented
- Auth, tenancy, DB migrations, procurement core, document pipeline, Copilot, Android app, prod hardening
