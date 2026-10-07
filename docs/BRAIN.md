<!-- vantor-brain-link -->
> You are in the 🧠 **VANTOR Brain** — mirror index: [Docs index](README.md).

# 🧠 VANTOR Brain — central knowledge index

> **Start here.** Every document in this repo links back here, and this brain links to every document. No orphan pages.
> Mirror index: [`docs/README.md`](README.md) · Root: [`../README.md`](../README.md) · Roadmap: [`00-plan/ROADMAP.md`](00-plan/ROADMAP.md)
> 🚀 **Live Portal on Vercel:** [VANTOR — Intelligent Procurement Operating System](https://vantor-os.vercel.app/)

## How to read VANTOR in 5 minutes

1. Vision + status → [`../README.md`](../README.md)
2. **The 10 products** → [`01-product/portfolio.md`](01-product/portfolio.md) (canonical list)
3. What we found → [`00-plan/REPOSITORY_AUDIT.md`](00-plan/REPOSITORY_AUDIT.md) (VERIFIED 2026-09-26: 5/5 repos, ~775 files — audit scope, not product count)
4. How 5 repos become 1 platform → [`00-plan/MIGRATION_PLAN.md`](00-plan/MIGRATION_PLAN.md)
5. Build order → [`00-plan/ROADMAP.md`](00-plan/ROADMAP.md)
6. Shared language → [`glossary.md`](glossary.md)

## Knowledge graph

```mermaid
flowchart TD
    BRAIN[VANTOR Brain] --> PRD[01-product/requirements]
    BRAIN --> PORT[01-product/portfolio]
    BRAIN --> SYS[02-architecture/system]
    BRAIN --> DOM[02-architecture/domain]
    BRAIN --> DB[02-architecture/database]
    BRAIN --> API[02-architecture/api]
    BRAIN --> AI[03-ai/architecture]
    BRAIN --> SAFE[03-ai/safety]
    BRAIN --> EVAL[03-ai/evaluation]
    BRAIN --> SEC[04-security/architecture]
    BRAIN --> THREAT[04-security/threat-model]
    BRAIN --> UI[05-frontend/design-system]
    BRAIN --> BRAND[06-brand/logo]
    BRAIN --> ANDROID[07-android/strategy]
    BRAIN --> DEPLOY[08-deployment/local]
    BRAIN --> OPS[09-operations/runbook]
    BRAIN --> ADR[10-decisions]
    PRD --> DOM --> DB --> API --> AI
    PORT --> PRD
    PORT --> ROADMAP[00-plan/ROADMAP]
    API --> ANDROID
    AI --> SAFE --> EVAL
    SEC --> THREAT
    SYS --> DEPLOY --> OPS
    UI --> BRAND
```

## Every document (bidirectional — each links back here)

| # | Document | Answers | Status |
|---|---|---|---|
| 0 | [`../README.md`](../README.md) | What is VANTOR, quickstart, layout | IN DEVELOPMENT |
| 0 | [`00-plan/ROADMAP.md`](00-plan/ROADMAP.md) | Phases 0–11 with per-phase gaps + reporting rules | TESTED 3–4 |
| 0 | [`00-plan/REPOSITORY_AUDIT.md`](00-plan/REPOSITORY_AUDIT.md) | 5-repo audit matrix (audit scope, not product count) | VERIFIED |
| 0 | [`00-plan/MIGRATION_PLAN.md`](00-plan/MIGRATION_PLAN.md) | KEEP/ADAPT/MERGE/… plan | PLANNED |
| 0 | [`00-plan/SESSION.md`](00-plan/SESSION.md) | Session handoff / resume guide | IMPLEMENTED |
| 0 | [`00-plan/audit-findings/MASTER_FINDINGS.md`](00-plan/audit-findings/MASTER_FINDINGS.md) | 45-item evidence-backed defect/risk register | VERIFIED |
| 0 | [`00-plan/audit-findings/RE_AUDIT_2026-10-02.md`](00-plan/audit-findings/RE_AUDIT_2026-10-02.md) | Current live-reproduced findings, release-blocker matrix, release decision | VERIFIED |
| 1 | [`01-product/requirements.md`](01-product/requirements.md) | PRD: modules, graph, non-negotiables | PLANNED |
| 1 | [`01-product/portfolio.md`](01-product/portfolio.md) | **Canonical list of the 10 products** + per-product status | IN DEVELOPMENT |
| 2 | [`02-architecture/system.md`](02-architecture/system.md) | Modular monolith, free topology | PLANNED |
| 2 | [`02-architecture/domain.md`](02-architecture/domain.md) | 60-entity domain model | PLANNED |
| 2 | [`02-architecture/database.md`](02-architecture/database.md) | Postgres+pgvector, RLS | PLANNED |
| 2 | [`02-architecture/api.md`](02-architecture/api.md) + [`../api/openapi.yaml`](../api/openapi.yaml) | REST contract, typed AI tools | PLANNED |
| 3 | [`03-ai/architecture.md`](03-ai/architecture.md) | Gateway, evidence, HITL, pipeline | PLANNED |
| 3 | [`03-ai/safety.md`](03-ai/safety.md) | Injection defense | PLANNED |
| 3 | [`03-ai/evaluation.md`](03-ai/evaluation.md) | Eval gates | PLANNED |
| 4 | [`04-security/architecture.md`](04-security/architecture.md) | OIDC/RBAC/RLS/audit | PLANNED |
| 4 | [`04-security/threat-model.md`](04-security/threat-model.md) | STRIDE threats | PLANNED |
| 5 | [`05-frontend/design-system.md`](05-frontend/design-system.md) | Tokens + components (dark mode + fonts still due) | IN DEVELOPMENT |
| 6 | [`06-brand/logo.md`](06-brand/logo.md) + [`../assets/brand/`](../assets/brand/) | Vantor identity | IMPLEMENTED art |
| 7 | [`07-android/strategy.md`](07-android/strategy.md) | Kotlin/Compose plan | COMING SOON (API-ready) |
| 8 | [`08-deployment/local.md`](08-deployment/local.md) + [`../docker-compose.yml`](../docker-compose.yml) | Free local stack | IMPLEMENTED compose |
| 9 | [`09-operations/runbook.md`](09-operations/runbook.md) | Health/backup/incidents + RLS session discipline | IMPLEMENTED |
| 10 | [`10-decisions/README.md`](10-decisions/README.md) | ADR index (001–006) | Accepted |
| X | [`glossary.md`](glossary.md) | Ubiquitous language | IMPLEMENTED |

Products 06–10 shipped as native modules (`sourcing/`, `spend/`, `suppliers/`, `ai/` — see
[`01-product/portfolio.md`](01-product/portfolio.md)); their original vendored spec bundle has
been retired now that the modules and this documentation set are the source of truth.

## Concept trails (follow the brain, not folders)

- **New developer:** Brain → portfolio → glossary → system → database → api → local → runbook.
- **New auditor:** Brain → threat-model → security/architecture → audit events (domain) → runbook incidents.
- **New AI engineer:** Brain → portfolio (01, 10) → ai/architecture → safety → evaluation → api (tools) → domain (AIEvidence).
- **New designer:** Brain → portfolio → brand/logo → design-system → android/strategy.
- **New DevOps:** Brain → system → local → runbook → decisions/ADR-001,002,005.

## Brain maintenance rule

Any new `.md` added anywhere MUST: (1) add a row above, (2) prepend the standard breadcrumb header (verified by `python scripts/verify_brain_links.py`), (3) appear in `docs/README.md` + `mkdocs.yml` nav. CI docs gate enforces this.
