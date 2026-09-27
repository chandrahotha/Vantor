<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Current UI Audit

The UI has useful shared primitives and accessibility intent, but the current implementation still relies on many page-local inline styles and generic grids. Its main weakness is information architecture and decision flow, not simply color/spacing. The redesign should preserve functional patterns that are good (shared `DataTable`, `Empty`, `ErrorBox`, `Skeleton`, auth boot) while replacing the overall visual hierarchy and task model.
