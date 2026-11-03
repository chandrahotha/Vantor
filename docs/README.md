# Documentation — VANTOR

Everything about how VANTOR is built, secured, deployed and operated. Each
page is written to be read on its own.

**Start here:** the [knowledge index](BRAIN.md) maps how the documents
relate to each other.

## Reading order

**If you are evaluating VANTOR**

1. [System architecture](02-architecture/system.md) — how the pieces fit together
2. [Security architecture](04-security/architecture.md) — auth, tenancy, RBAC, audit
3. [Database architecture](02-architecture/database.md) — schema, row-level security, vectors
4. [AI architecture](03-ai/architecture.md) — gateway, typed tools, evidence contracts

**If you are deploying it**

1. [Local deployment](08-deployment/local.md) — every environment variable
2. [Operations runbook](09-operations/runbook.md) — health, backup, incidents
3. [Security architecture](04-security/architecture.md)

**If you are working on it**

1. [Domain model](02-architecture/domain.md) — the vocabulary, in code
2. [API design](02-architecture/api.md) — envelopes, pagination, idempotency, errors
3. [Design system](05-frontend/design-system.md) — tokens, palettes, primitives
4. [Decisions](10-decisions/README.md) — the ADRs and why they were taken

## The documents

| Document | What it covers |
|---|---|
| [BRAIN.md](BRAIN.md) | Knowledge index — how the documents connect |
| [glossary.md](glossary.md) | Shared vocabulary across the platform |
| [01-product/requirements.md](01-product/requirements.md) | Product requirements |
| [01-product/portfolio.md](01-product/portfolio.md) | The capability map and where each capability lives |
| [02-architecture/system.md](02-architecture/system.md) | System architecture, deployment topology |
| [02-architecture/domain.md](02-architecture/domain.md) | Domain model and entities |
| [02-architecture/database.md](02-architecture/database.md) | Schema, tenancy, row-level security, vectors |
| [02-architecture/api.md](02-architecture/api.md) | API conventions, envelopes, pagination, idempotency |
| [03-ai/architecture.md](03-ai/architecture.md) | AI gateway, typed tools, providers |
| [03-ai/safety.md](03-ai/safety.md) | Evidence contracts, human review, guardrails |
| [03-ai/evaluation.md](03-ai/evaluation.md) | How AI behaviour is evaluated |
| [04-security/architecture.md](04-security/architecture.md) | Authentication, authorisation, tenancy, audit |
| [04-security/threat-model.md](04-security/threat-model.md) | Threats, mitigations, residual risk |
| [05-frontend/design-system.md](05-frontend/design-system.md) | Tokens, palettes, components, accessibility |
| [06-brand/logo.md](06-brand/logo.md) | Logo assets and usage |
| [07-android/strategy.md](07-android/strategy.md) | Android client strategy |
| [08-deployment/local.md](08-deployment/local.md) | Environment variables, compose, deployment modes |
| [09-operations/runbook.md](09-operations/runbook.md) | Health checks, backup, incident response |
| [10-decisions/](10-decisions/README.md) | Architecture decision records |
| [12-legal/](12-legal/README.md) | Draft legal templates — **not legally reviewed** |

## Root companions

[`../README.md`](../README.md) ·
[`../SECURITY.md`](../SECURITY.md) ·
[`../CONTRIBUTING.md`](../CONTRIBUTING.md) ·
[`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) ·
[`../CHANGELOG.md`](../CHANGELOG.md)

Bugs and feature requests belong in
[GitHub Issues](../../issues), not in a register file in the repository.
Security reports go through [`../SECURITY.md`](../SECURITY.md) — privately.
