<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Security Architecture - VANTOR

**Status: `PLANNED`. Enforced from Phase 3.**

## AuthN/Z
Keycloak OIDC/SSO + MFA; short JWT + rotating refresh; server-side session revocation. RBAC roles (Super/Org/Procurement Admin, Manager, Buyer, Category/Supplier Mgr, Finance/Legal, Approver, Auditor, Supplier User, Read-Only) + scopes + resource-level checks + spending limits. `tenant_id` RLS + tenant-aware cache/search/storage/logs/AI.

## Data protection
TLS in transit; encrypted at rest (managed volumes/KMS in prod); per-env secrets manager; `.env.example` only in git. Uploads: allowlist, size caps, object-storage only, malware-scan hook, no execution. Rate limits, security headers, CORS allowlist, CSRF where applicable, input validation + output encoding.

## Audit
Immutable `audit_events(actor,tenant,action,resource,resource_id,timestamp,ip/device,before,after,reason,approval,source)` covering `SUPPLIER_* RFQ_* QUOTE_* CONTRACT_* PO_* INVOICE_* APPROVAL_* AI_TOOL_EXECUTED`. Tamper-evident retention per policy.

## Supply chain
Pinned images, lockfiles, `npm/pip audit`, container + migration scans in CI, SBOM at release.
