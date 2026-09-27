<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Documentation Drift Register

The current repository contains several inconsistent counts and maturity statements. Examples observed during the re-audit include:

- README references 113 backend tests while actual current execution produced 155 passed.
- Different documents report different API/route counts.
- Frontend documentation describes an older state than the current source, despite frontend test files now existing.
- Current source uses Next 16.3.6 / React 19.3.0 while some planning documents describe older versions.

Required fix:

Create one generated `PROJECT_STATUS.md` in CI that derives versions, route counts, test counts and feature readiness from source/manifests. Historical planning documents must be labeled historical and never used as deployment instructions without verification.
