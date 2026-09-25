<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# Security Policy — VANTOR

**Status: `PLANNED` + enforced from Phase 3 onward.**

## Supported versions

| Version | Supported |
|---|---|
| `main` (V1 scaffold) | Best effort (no running production yet) |
| Future `1.x` releases | Security patches documented in CHANGELOG |

## Reporting a vulnerability

- **Do not open a public issue for vulnerabilities.**
- Email the maintainers privately (add `SECURITY_CONTACT` before public launch).
- Include: affected version/commit, reproduction steps, impact, suggested mitigation.
- Expect acknowledgement within 72h, triage within 7 days once `1.0` ships.

## Guaranteed controls (Definition of Done)

- OIDC (Keycloak) + MFA, short-lived JWT + rotating refresh tokens
- RBAC + resource-level authz + `tenant_id` RLS on every query
- Tenant-aware cache/search/storage/logs/AI context — cross-tenant tests mandatory
- TLS everywhere, encryption at rest (managed disk/KMS in prod), secret manager (never `.env` in git)
- Validated uploads (type/size), object storage only, malware-scan hook, OCR sandboxing
- Rate limiting, security headers, CORS allowlist, CSRF where cookies used
- Immutable audit log for all significant actions + AI tool calls
- `npm audit` / `pip audit` + container + migration checks in CI (`/.github/workflows/ci.yml`)
- AI treated as untrusted-input boundary: typed tools only, no raw SQL/shell, prompt-injection defenses (`docs/03-ai/safety.md`)

## Out of scope

Social engineering, physical attacks, third-party SaaS misconfigurations outside Vantor defaults.
