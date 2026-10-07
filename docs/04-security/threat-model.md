<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Threat Model - VANTOR (STRIDE-lite)

**Status: `PLANNED`. Review each release.**

## Assets
Procurement PII/financials, contracts, supplier bank details, credentials, embeddings, audit log.

## Top threats → mitigations
- **Cross-tenant leak (info disclosure):** RLS + tenant-aware everything + isolation tests. Residual: migration bug → canary + rollback.
- **Privilege escalation (elevation):** resource authz + server-side limit checks + approval workflows. Residual: misconfigured role → quarterly access review.
- **Prompt/doc injection (spoofing/tampering):** `../03-ai/safety.md` pipeline + HITL for financial moves.
- **Malicious upload (tampering/DoS):** type/size validation, sandbox, async processing, quotas.
- **Token theft (spoofing):** short JWT, rotation, revocation, MFA for high-risk roles.
- **SSRF via integrations (tampering):** egress allowlist, no creds in logs, webhook signing.
- **Audit tampering (repudiation):** append-only store, separate retention, alerting on gaps.

Out of scope: attacker with cloud-admin; compromised IdP beyond Vantor config (document dependency).
