<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Security Architecture - VANTOR

**Status: `PARTIALLY IMPLEMENTED`.** The list below is split into what the code
enforces today and what is only designed, because the previous version of this
page stated both in one present-tense paragraph — and a security document that
reads as shipped is worse than no document, since it is what an assessor, an
operator and a new developer all trust. `scripts/` gates and the test suite are
the authority on which half is which.

## AuthN/Z — implemented

- **Two identity modes, one verification path.** `AUTH_MODE=oidc` verifies
  RS256 tokens against the issuer's JWKS; `AUTH_MODE=local` mints its own.
  `jwt.decode` pins `iss`, `aud`, `exp` and requires a tenant claim, so a forged
  or wrong-audience token is refused in every environment including development
  (`tests/test_auth.py`, `test_realm_parity.py`).
- **Browser sign-in through the IdP** (authorization code + PKCE, S256).
  `vantor-web` is provisioned as a public client, which is the only correct
  shape for a browser: a secret in a bundle is not a secret. The SPA gets the
  authorization and token endpoints from `GET /auth/config`, which derives them
  from the same `OIDC_ISSUER` this process verifies against — so there is one
  source of truth for which realm the user logs into and whose keys are
  accepted. See `frontend/lib/oidc.ts` and `deploy/keycloak/provision.py`.
  **The operator must list the web origin in `WEB_ORIGINS`**, or Keycloak will
  refuse the redirect and login cannot complete.
- **RBAC** with role names held in the database, not in code paths, plus
  resource-level checks, segregation of duties on approvals and quorum rules.
- **Tenancy**: `tenant_id` on every tenant-scoped table, application filters plus
  PostgreSQL row-level security. RLS only protects you if the runtime role is
  non-superuser and does not own the tables — the API now checks that at startup
  and refuses it in production (see the runbook §7 hard rule).
- **Session credentials**: short-lived access tokens; the OIDC refresh token is
  kept in `sessionStorage` (this tab only) rather than `localStorage`, so it does
  not outlive the tab. The access token is still readable by XSS — that is the
  known exposure below, not a solved one.

## AuthN/Z — designed, not implemented

- **MFA.** No TOTP/WebAuthn code exists in this repository.
- **Server-side session revocation.** There is no `jti` claim, no denylist and no
  revocation endpoint; a token is valid until it expires. Signing out ends the
  local copy.
- **Per-user supplier identity.** "Supplier User" is a role name; there is no
  supplier-scoped login or portal yet, so a supplier cannot act on their own
  records.
- **Delegated approval / out-of-office**, SCIM provisioning, and per-user
  spending limits beyond the role-level ones.

## Data protection

TLS in transit and encryption at rest are the **operator's** deployment
responsibility — this repository configures neither; managed volumes/KMS are
documented, not wired. `.env.example` is the only env file in git; secrets are
validated at production start (`require_prod_secrets`) for the variables this
process actually reads. Uploads: extension and size allowlists, compression-ratio
and archive-entry caps, content-addressed storage, quarantine on failure.
**No malware scan** is implemented. Rate limits, security headers, a CORS
allowlist and input validation are implemented; CSRF is not applicable to the
bearer-token API but the local session endpoint is unauthenticated by design.

## Audit

Immutable `audit_events(actor,tenant,action,resource,resource_id,timestamp,ip/device,before,after,reason,approval,source)` covering `SUPPLIER_* RFQ_* QUOTE_* CONTRACT_* PO_* INVOICE_* APPROVAL_* AI_TOOL_EXECUTED`, hash-chained with a verifier endpoint (`GET /audit-events/verify`). Retention per policy is **not** implemented. A swallowed audit write is now counted and logged rather than lost silently (`vantor_degraded_operations`).

## Supply chain

Container images and Dockerfile bases are digest-pinned and gated
(`scripts/pin_digests.py`, including cross-file agreement between compose and
CI); lockfiles committed; `pip-audit --strict` and `npm audit --audit-level=high`
run in CI; migration chain audited. **No SBOM is produced at release** and
**GitHub Actions are pinned by floating major tag, not digest.**
