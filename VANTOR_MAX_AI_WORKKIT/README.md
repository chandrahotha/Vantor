<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# VANTOR MAX AI WORKKIT

## Purpose

This package is the **current-code re-audit + autonomous engineering blueprint** for the VANTOR repository supplied as `Vantor-main.zip`.

The objective is not to describe an ideal greenfield application. The coding agent must take the **existing VANTOR repository as the system to repair**, re-read the live source before every material change, implement the fixes and improvements in dependency order, and prove the result with automated verification.

Target outcome:

- zero known Critical/High defects;
- no open financial-integrity race conditions;
- deterministic, auditable state transitions;
- secure multi-tenant behavior;
- durable document and integration pipelines;
- production-grade deployment and recovery;
- Grade-5 enterprise UI/UX;
- complete E2E/user journey coverage;
- measurable performance, observability and SRE controls;
- generated documentation that matches the actual source.

**10/10 is an acceptance target, not a claim that software can be mathematically guaranteed bug-free.** Release only when the gates in `22_ACCEPTANCE/10_OF_10_ACCEPTANCE_GATE.md` are satisfied.

## Evidence hierarchy

1. Current source code in the repository.
2. Current automated tests and their execution output.
3. Current migrations/schema/configuration.
4. Current API contracts/OpenAPI.
5. Committed documentation and roadmap files.

When documentation conflicts with source or tests, the agent must treat the source/test state as authoritative, then update the documentation.

## Start here

1. `00_MASTER_CONTROL/MASTER_EXECUTION_PROMPT.md`
2. `00_MASTER_CONTROL/AGENTS.md`
3. `01_CURRENT_RE_AUDIT/CURRENT_BASELINE.md`
4. `01_CURRENT_RE_AUDIT/ACTUAL_VERIFICATION.md`
5. `02_FINDINGS/MASTER_FINDINGS.md`
6. `19_IMPLEMENTATION_MAP/FILE_BY_FILE_CHANGE_MAP.md`
7. `20_PHASES/PHASE_INDEX.md`
8. `22_ACCEPTANCE/10_OF_10_ACCEPTANCE_GATE.md`

## Important current evidence

The supplied repository contains **671 files**: 131 Python files, 35 TSX files, 10 TypeScript files, 331 Markdown files, 5 worker files, and 20 Alembic migrations. The current backend test run completed with **155 passed, 2 skipped in 28.31s** in the supplied environment. The two skipped tests require PostgreSQL infrastructure that was not available in the execution environment. Frontend dependency installation/build verification did not complete in the local audit environment; CI must remain authoritative for the browser build until reproduced.

## Package structure

- `01_CURRENT_RE_AUDIT` — current repository facts and test evidence.
- `02_FINDINGS` — individual findings with evidence, remediation and test requirements.
- `03_ARCHITECTURE` — target architecture and boundaries.
- `04_BUSINESS_RULES` — business invariants and policy catalog.
- `05_STATE_MACHINES` — explicit lifecycle/state transition contracts.
- `06_FINANCIAL_CONTROLS` — money, approval, ledger and concurrency safety.
- `07_SECURITY` — threat model and hardening.
- `08_DOCUMENT_AI` — document pipeline and AI evidence safety.
- `09_INTEGRATIONS` — outbox/retry/adapter reliability.
- `10_APIS` — contract and API consistency.
- `11_DATABASE` — schema, RLS, migrations and recovery.
- `12_FRONTEND_GRADE5` — full UI redesign and screen specifications.
- `13_USE_CASES` — operational user journeys.
- `14_REGION_LOCALIZATION` — regionalization/compliance blueprint.
- `15_TESTING_QA` — complete quality strategy.
- `16_PERFORMANCE_SRE` — performance/scalability/SRE.
- `17_DEPLOYMENT` — real deployment hardening.
- `18_CI_CD_SUPPLY` — CI/CD and software supply-chain gates.
- `19_IMPLEMENTATION_MAP` — source-to-change mapping.
- `20_PHASES` — ordered autonomous execution prompts.
- `21_LLM_BRAINS` — specialized coding-agent reasoning packs.
- `22_ACCEPTANCE` — 10/10 release gates.
