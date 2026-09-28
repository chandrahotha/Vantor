<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Tenant Isolation

Enforce tenant isolation at three levels: JWT-to-request tenant binding, every query/write scoped to tenant, PostgreSQL RLS where appropriate. Add cross-tenant attack tests for every resource type and every route family.

## Now implemented (2026-09-28)

All three levels are in place: the tenant is bound from the JWT into a pinned session
(`app.core.tenant`), every query carries an explicit `tenant_id` predicate, and Postgres RLS
policies on the tenant tables are fail-closed — `current_setting('app.tenant_id', true)` is
NULL without a context, so no context means no rows.

Known gaps, stated rather than implied:

- **The RLS guard only covers the baseline migration.** `test_tenant_isolation.py` asserts
  that `0001_baseline.py` defines its policies, but the 13 later migrations that also enable
  RLS are not covered by any test. A *new* tenant table could therefore ship with no policy and
  the suite would stay green. This is the most consequential thing still open here.
- All 137 `select()` calls in the routers and services were audited for the shape that looks
  correctly filtered but is not tenant-scoped — `where(id == ...)` with no tenant. 133 carry a
  tenant predicate. Of the four that do not, three delegate to a correct helper
  (`_visible(actor)`) and one was a real defect: `drain()` defaulted its tenant scope to
  "every tenant", so a caller omitting the argument would have sent every tenant's queued
  webhook payloads to every tenant's endpoints. Fixed, and the property now has a test that
  was mutation-checked. Modify/delete statements were audited the same way and are clean.
- Cross-tenant attack tests exist per resource family, but there is no generated
  per-route/per-model matrix, which is what "every route family" would actually require.
