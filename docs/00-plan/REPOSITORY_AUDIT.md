<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# REPOSITORY AUDIT — VANTOR

**Status: `BLOCKED` — private repositories not accessible from this environment.**

Target repos (all private, in active development per owner):

1. `https://github.com/chandrahotha/SupplierRadar--Valtrix` — supplier intelligence
2. `https://github.com/chandrahotha/ContractGuard-Veridox` — contract intelligence
3. `https://github.com/chandrahotha/CostPilot-Costryn` — cost intelligence
4. `https://github.com/chandrahotha/RFQLens-QuotientX` — sourcing/RFQ intelligence
5. `https://github.com/chandrahotha/ProcurementOS-Agent` — procurement AI agent

## Audit matrix (fill in Phase 0 once access granted)

| Repository | Technology (lang/fw/DB) | Features | Reusable as-is | Needs adapt/refactor | Rewrite | Risk / blockers |
|---|---|---|---|---|---|---|
| SupplierRadar-Valtrix | UNKNOWN — needs inspection | supplier discovery/profiles/scorecards (assumed) | TBD | TBD | TBD | access pending |
| ContractGuard-Veridox | UNKNOWN | repo/OCR/clauses/obligations (assumed) | TBD | TBD | TBD | access pending |
| CostPilot-Costryn | UNKNOWN | spend/savings/benchmarks (assumed) | TBD | TBD | TBD | access pending |
| RFQLens-QuotientX | UNKNOWN | RFQ/quotes/compare/award (assumed) | TBD | TBD | TBD | access pending |
| ProcurementOS-Agent | UNKNOWN | copilot/tools/prompts (assumed) | TBD | TBD | TBD | access pending |

**Do NOT assume internals. Do NOT merge blindly. Decisions in `MIGRATION_PLAN.md` only after this table is filled with evidence (file paths + commit SHAs).**

## How to unblock (owner action)

Option A (recommended): `gh auth login` then add temp read access, or push mirrors.
Option B: upload 5× `.zip` / `git bundle` into `C:\Users\hotha\AppData\Local\Temp\opencode` equivalent.
Option C: paste per-repo `package.json`/`requirements.txt` + `Dockerfile` + tree output; audit proceeds as provisional.

## Provisional stack decision (reversible via ADR)

Backend language deferred until audit proves TS vs Python dominance.
Default hypothesis: **NestJS API core + Python ai-worker sidecar** if both ecosystems present; else single-stack to minimize ops. See `docs/10-decisions/ADR-001-modular-monolith.md`.
