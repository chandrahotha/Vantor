# 10/10 Acceptance Gate

## Gate A — Correctness

- [ ] Zero open Critical defects.
- [ ] Zero open High defects.
- [ ] Every verified finding has a regression test.
- [ ] All state machines have exhaustive transition tests.

## Gate B — Financial integrity

- [ ] Cumulative invoice quantity/value invariant enforced transactionally.
- [ ] Budget reservations are atomic.
- [ ] Receipt cumulative checks are atomic.
- [ ] Commitments/actuals are idempotent and uniquely constrained.
- [ ] Currency and FX rules are explicit.
- [ ] Ledger reconciliation produces zero unexplained differences.

## Gate C — Security

- [ ] Authentication/authorization matrix tested.
- [ ] Tenant isolation tested at API and DB layers.
- [ ] SSRF protection tested.
- [ ] Upload/parser abuse tested.
- [ ] CSP and browser security headers verified.
- [ ] No production default secrets/credentials.
- [ ] Supply-chain gates pass.

## Gate D — Reliability

- [ ] Idempotency is atomic.
- [ ] Outbox/webhook retry/DLQ/replay works.
- [ ] Object storage survives replica/container restart.
- [ ] Worker and scheduler have durable observability.
- [ ] Backup restore has been demonstrated.

## Gate E — UI Grade 5

- [ ] Shared design system used by all primary screens.
- [ ] No major inline-style duplication.
- [ ] First-class Approval Center and Invoice workspace exist.
- [ ] Desktop/tablet/mobile visual tests pass.
- [ ] WCAG 2.2 AA automated and manual checks pass for core journeys.
- [ ] Empty/error/loading/partial data states are deliberate.

## Gate F — Performance/SRE

- [ ] PostgreSQL indexes/query plans validated at target data volume.
- [ ] No blocking network/Redis calls on critical async paths.
- [ ] Search meets target latency and relevance checks.
- [ ] SLOs, dashboards and alerts exist.
- [ ] Load test and degradation behavior are documented.

## Gate G — Production deployment

- [ ] Immutable container images.
- [ ] Private data services.
- [ ] Keycloak bootstrap as code.
- [ ] Secrets from secret manager.
- [ ] Controlled migrations.
- [ ] Smoke E2E after deployment.
- [ ] Rollback tested.
- [ ] Restore drill passed.

## Final rule

No “10/10” label is allowed in release notes until every checked item has current evidence attached to the release record.
