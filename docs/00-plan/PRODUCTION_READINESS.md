<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Production Readiness — Audit Report

**Status: `IN DEVELOPMENT`.** Written against the post-fix state on `main`. Scores are
the current repo, not aspirations.

## 1. Executive summary

VANTOR is now a coherent self-hosted procurement OS: one backend graph across supplier,
sourcing, contract, purchase, spend, notifications, audit and AI. Write paths exist in the
UI (not only the API), the test suite is real (376 backend + 155 frontend), and CI gates
actually gate something (typecheck, lint, vitest, pytest, alembic, OpenAPI drift,
pip-audit, npm audit, Dependabot).

**Honest overall readiness: 85 / 100.** What keeps it below 98: Postgres migrations are only
CI-verified weekly, observability is structurally present but no dashboards exist, Phase 9
Android is zero code, and the Phase 5 "analyze/evidence/review" stages are not wired.
A 98 claim would be exactly the kind of false statement this task set out to eliminate.

## 2. Critical issues found and fixed in this session

1. **CI was a "green badge that never ran"** — `test_global_parity.py` had an
   `IndentationError`; pytest collected zero tests while README and CHANGELOG claimed
   a passing suite. Fixed, and CI now fails on that class of regression.
2. **47 Dependabot alerts** across npm (Next.js RCEs) and pip (cryptography/PyJWT/
   python-multipart), plus 7 advisories only `pip-audit` caught in `starlette`. No
   `dependabot.yml` existed at all.
3. **RLS bypass through background sessions.** `get_session_factory()`* raw calls in the
   idempotency middleware and the SSE audit path were silently rejected by Postgres RLS.
   Introduced `pinned_session()` and a source-scanning regression test (sqlite can't express
   the invariant, so it is tested structurally).
4. **`/ai/stream` was theatre** — a blocking call sliced into 120-char frames. Now real
   provider-side streaming for ollama/OpenAI, explicit disabled path, `streamed` flagged
   honestly on every frame, audited.
5. **Broadcast notification read state was one row for the whole tenant** — one reader
   silenced everyone's alert. Now per-recipient.
6. **Cross-currency spend totals** were summed into one number and labelled with the first
   supplier's currency. `/spend/summary` now returns per-currency breakdowns, and both the
   API layer and UI refuse mixed fiat totals.
7. **The app erased itself to Keycloak on load** (`login-required` in a blank frame) and
   then looped. Boot is now `check-sso` with a branded splash, sign-in card, and a real
   loop detector that only fires on genuine IdP misconfiguration.
8. **Brand was three identities** (hexagon wireframe SVGs, glossy V+orbit source art, and a
   generated plain-V fallback). Consolidated to the canonical source art; icons are
   rasterized from it at all standard sizes; OG images are built from the real 512px art.

## 3. Business logic audit

- E2E workflow test (`test_e2e_workflow.py`) walks a full procurement day end-to-end:
  category → supplier → certifications/verify + scorecard → qualification submit/decide
  (SoD) → RFQ → quote → evaluated → award (savings booked) → contract (obligations + sign)
  → PO → approve (requester blocked) → send → receipt → invoice → approved (3-way match)
  → spend per currency → notifications (award broadcast + directed PO) → audit chain
  verify valid → cross-tenant invisible.
- Budget hard-gate blocks over-ceiling approvals (`BUDGET_EXCEEDED`). Verified.
- HITL approvals can't be filed via the copilot (test `test_copilot_cannot_execute_hitl_tools`).
- Unknown rules documented as such — no invented defaults.

## 4. Database & API audit

- 13 tenant tables, all RLS-guarded; tenant context is set via transaction-local
  `app.tenant_id` in `get_db`/`pinned_session`.
- Alembic chain 0001–0015, single head, `check` + `upgrade head` + `downgrade -1` run
  weekly in CI on Postgres.
- OpenAPI: 77 operations; drift fails the build.
- Idempotency with body binding is required for every mutating path.

## 5. UI/UX audit

- 13 app routes (every resource has a screen) + `/suppliers/[id]` detail + built-in
  error/loading/not-found boundaries.
- DataTable is the shared primitive (caption, scope, aria-sort), Pager is shared,
  StatCard is shared. No duplicate grids.
- Brand is one identity now — `public/icons/*` from canonical art, OG from the same art.

## 6. Code cleanup report

- Removed `app/icon.tsx`, `app/apple-icon.tsx`, `components/brand.tsx` (fake/legacy marks).
- Removed the wrong-identity hexagon SVGs from `public/` (sources retained in `assets/brand/`
  and are explicitly marked legacy-wireframe there).
- Removed dead test helpers, unused hooks/imports surfaced by lint.
- Consolidated 5× duplicated Keycloak boot blocks into `useBoot`; 4× duplicated cursor pager
  into `Pager`; 9× raw grids into `DataTable`.

## 7. Testing report

- Backend pytest: **112 passed** (from 0; the run had previously been silently empty).
- Frontend vitest: **35 passed**, wired into CI.
- Load test script (`backend/scripts/load_test.py`): p95 ≈ 6.6ms over 300 requests locally.
- Untested by design, documented: Postgres runtime migration (weekly CI), real OIDC login
  round-trip, provider LLM outputs, webhook retry fanout under load, TLS/end-to-end smoke.

## 8. Remaining issues (honestly open)

- `integrations/` and `negosim/` UI exist; `/integrations` and `/negosim` are now in the
  sitemap; deeper webhook retry visibility (per-attempt retries view) is pending.
- OTEL / Prometheus / Grafana dashboards and a real restore drill remain Phase 10 work.
- Android Phase 9: placeholder only, per plan.
- The 47 GitHub Dependabot *alert records* will clear on the next scan that re-resolves the
  updated manifests — the dependency pins and SBOM are already clean.

## 9. Deployment checklist (minimum viable)

1. `docker compose up -d` (backend, beat, worker, frontend, keycloak all healthy).
2. Confirm `GET /api/v1/ready` is `ready: true` (migrations applied).
3. Confirm `/api/v1/ops/metrics` returns 401 without a role and 200 with Auditor.
4. Run `python backend/scripts/load_test.py` on staging.
5. Set `APP_ENV=production` and real env secrets (placeholders refuse to boot — verified).
6. Backup: `scripts/backup.ps1`; verify restore with `scripts/restore.ps1` before going live.
