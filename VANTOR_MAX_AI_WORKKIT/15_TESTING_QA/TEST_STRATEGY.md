<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Test Strategy

Test pyramid: unit/domain -> service/integration with PostgreSQL -> browser E2E -> visual/a11y -> security -> load/chaos/recovery. Every defect gets a regression test at the lowest meaningful level plus an end-to-end test for critical user journeys.
