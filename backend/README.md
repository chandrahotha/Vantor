<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

# Backend placeholder — VANTOR

**Status: `PLANNED`.**

Language/framework decided after `REPOSITORY_AUDIT.md` (hypothesis: NestJS core + Python ai-worker sidecar; single-stack if audit proves one ecosystem dominant).

Planned layout: `src/modules/{identity,supplier,sourcing,contract,spend,purchase,approval,workflow,document,ai,notification,integration,audit}/` + `src/common/` + `migrations/`.
API: `/api/v1/...`, OpenAPI, typed schemas, idempotency, versioning.
