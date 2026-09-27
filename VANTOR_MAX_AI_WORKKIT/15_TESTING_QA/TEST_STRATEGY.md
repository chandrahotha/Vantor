# Test Strategy

Test pyramid: unit/domain -> service/integration with PostgreSQL -> browser E2E -> visual/a11y -> security -> load/chaos/recovery. Every defect gets a regression test at the lowest meaningful level plus an end-to-end test for critical user journeys.
