<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Session Handoff — VANTOR

**Last updated: 2026-09-27. Branch `main` = `origin/main`.**

> **Before you plan anything:** read [`SCORECARD.md`](SCORECARD.md). It says, in
> one place, what is strong, what is not, and the three unglamorous pieces of work
> that close the gap between "the code is good" and "the product is trustworthy".
> [`BUGS.md`](BUGS.md) is the per-defect register.

## Where we stand

- **Backend: implemented and green.** FastAPI + Postgres/RLS + Alembic (16 revisions, one head, no destructive `upgrade()`), Keycloak OIDC, canonical hashed audit writer, RQ worker + beat scheduler. 128 backend tests.
- **Frontend: implemented and green.** Next.js App Router, design system, 8 workspaces, 48 tests. `npm run typecheck && lint && test && build` all pass.
- **AI: real, evidence-first, never silent.** `/ai/stream` is provider-side token streaming for every vendor. `disabled` is the default and the honesty anchor (UNKNOWN, confidence 0.0).
- **Phase 0 audit: VERIFIED** (`00-plan/REPOSITORY_AUDIT.md`, `MIGRATION_PLAN.md`). Phases 3–8 and the frontend have landed; the earlier "next work" list on this page is retired.
- CI: weekly + manual dispatch by owner budget, with pytest, mypy-adjacent gates, the Alembic PG chain, an OpenAPI drift check, `pip-audit`, `npm audit`, and a mojibake guard.

## Resume on the new device

```powershell
gh auth login
gh repo clone chandrahotha/Vantor
Set-Location Vantor
Copy-Item .env.example .env
docker compose up -d postgres redis keycloak
docker compose up -d --build backend frontend worker beat
python scripts/verify_brain_links.py
python scripts/check_mojibake.py
```

`ollama` and `minio` are behind profiles — see `08-deployment/local.md`. The AI
gateway ships `disabled` on purpose: a fresh clone answers UNKNOWN rather than
failing to connect.

## Before you build

```powershell
# backend  (SQLite, no Postgres needed)
$env:APP_ENV=test; $env:DATABASE_URL=sqlite://
python -m pytest backend/tests -q
python -m mypy backend/app --ignore-missing-imports

# frontend
Set-Location frontend; npm ci; npm run typecheck; npm run lint; npm test
```

## Known limitations worth knowing

Every known defect, risk and deliberate omission is graded and tracked in
**[`BUGS.md`](BUGS.md)**. That file is the register; the summary below is only
what is most likely to surprise you mid-task.

- **No foreign keys anywhere.** 40 tables, zero `FOREIGN KEY`, zero
  `relationship()`. Referential integrity is enforced in the routers via
  `app/services/refs.py` (`require_ref`, `require_refs`, `require_no_cycle`).
  Adding real constraints is the single highest-value schema change available;
  it has not been done because it needs a data-cleanliness pass first
  (`BUGS.md` §5.1).
- **`organizations` / `user_accounts` / `roles` are dead tables.** Nothing reads
  or writes them. Authorization is a hard-coded `WRITE_ROLES` set per router, so
  `roles.permissions` is decorative. RBAC lands with the identity work.
- **Write-only tables:** `integrations` (adapters are a hard-coded dict),
  `contract_signatures` and `match_runs` (evidence written, never readable).
- **`requisitions` have no `requisition_id` on `purchase_orders`.** The
  "maverick" spend metric is therefore really an *uncategorised PO* metric.
- **An invoice or PO can never be rejected.** Only `approve` exists, so a bad
  invoice is permanently stuck at `received`.
- **All search is leading-wildcard `ILIKE`**, so the purpose-built name indexes
  are unusable and `document_chunks.text` is unindexed.
- **`price_intel.baseline_for`** is per-line by design; pass a `BaselineCache`
  when evaluating many lines in one request (`spend.py` does).
- **`CREATE EXTENSION vector`** is required at install but unused — embeddings
  are JSON arrays ranked with in-Python cosine.
- **Tests build the schema with `create_all` on SQLite**, so neither Alembic,
  `VARCHAR(n)` nor RLS is exercised. This is the blind spot that hid the
  idempotency-key overflow; it is `BUGS.md` §6.1 and the most important
  verification gap to close.

## Open items / risks

- RFQLens mock-as-done code must never be ported as-is (see audit § honesty check).
- Secrets: only placeholders in the repo; real Keycloak/DB creds live in local `.env` (never commit).
- CI is weekly + manual dispatch by owner budget — **nothing gates a merge**.
- OTEL tracing is still a Phase 10 item; the in-process metrics endpoint
  (`GET /api/v1/ops/metrics`) is the honest baseline.
- Repo is **private**; flip only on explicit `make public`.
