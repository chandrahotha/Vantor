# LLM Execution Checklist — Strategic Sourcing Optimization Engine

### Before coding
- [ ] Read `START_HERE_LLM.md`.
- [ ] Read inherited Top-5 contracts.
- [ ] Read all product files 00–23.
- [ ] Verify repository/runtime versions and record them.
- [ ] Create an ADR for any divergence.

### During coding
- [ ] Implement migration + model + service + endpoint + audit + test together.
- [ ] Keep deterministic engine independent of AI.
- [ ] Add golden vector before changing numerical logic.
- [ ] Add security regression test for each new input boundary.
- [ ] Add UI loading/empty/error/denied/stale states.
- [ ] Update API/event contracts before integration coding.

### Before release
- [ ] Clean-clone build succeeds.
- [ ] Full tests pass.
- [ ] Tenant isolation verified.
- [ ] SoD and material-action gates verified.
- [ ] Audit chain verified.
- [ ] Synthetic demo reset verified.
- [ ] Integration adapters tested with mocks.
- [ ] Deployment/runbook/release gate complete.
