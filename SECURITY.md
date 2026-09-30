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
- Email privately: **digi.tracks@outlook.com** (Digi Tracks).
- Include: affected version/commit, reproduction steps, impact, suggested mitigation.
- Expect acknowledgement within 72h, triage within 7 days once `1.0` ships.

## Guaranteed controls (Definition of Done)

- Two auth modes, one verification path: `AUTH_MODE=local` (default) makes the
  API its own issuer — RS256 tokens, no identity service, but **passwordless**
  (anyone who can reach the deployment is the operator; single-container/SQLite
  use only). `AUTH_MODE=oidc` requires Keycloak + MFA with short-lived JWT and
  rotating refresh tokens. Both modes verify the same way: a forged or
  foreign-signed token is a 401 either way.
- RBAC + resource-level authz + `tenant_id` RLS on every query
- Machine identities least-privilege by construction (see below)
- Tenant-aware cache/search/storage/logs/AI context — cross-tenant tests mandatory
- TLS everywhere, encryption at rest (managed disk/KMS in prod), secret manager (never `.env` in git)
- Validated uploads (type/size), object storage only, malware-scan hook, OCR sandboxing
- Rate limiting, security headers, CORS allowlist, CSRF where cookies used
- Immutable audit log for all significant actions + AI tool calls
- `npm audit` / `pip audit` + container + migration checks in CI (`/.github/workflows/ci.yml`)
- AI treated as untrusted-input boundary: typed tools only, no raw SQL/shell, prompt-injection defenses (`docs/03-ai/safety.md`)

## Where the Content-Security-Policy actually applies

A CSP delivered by one origin does **not** apply to documents served by another.
VANTOR runs the API and the web app on separate origins, and the pages a user
actually reads are served by Next — so the API's policy, however strict, was
never governing the application UI. Both hosts therefore set their own:

| Host | Where | Notes |
|---|---|---|
| API | `backend/app/core/secheaders.py` | No `unsafe-inline` for scripts. |
| Web app | `frontend/next.config.mjs` | Static headers, so correct on the first response. |

The app's `script-src` needs `'unsafe-inline'` because Next injects its own
bootstrap script into the document; a nonce cannot reach a build-time stylesheet
or script. That is stated in the config rather than hidden, and it is the one
directive weaker than the API's. Everything else is held tight: `default-src
'self'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`,
`frame-ancestors 'none'`, plus `X-Frame-Options: DENY`, `Referrer-Policy:
no-referrer` and a restrictive `Permissions-Policy`.

Allowed origins in the app's policy are **derived** from `NEXT_PUBLIC_API_URL` and
`NEXT_PUBLIC_KEYCLOAK_URL`, not hardcoded — a pinned `localhost:8000` would have
blocked the API call in every other deployment while looking correct in the source.
HSTS and `upgrade-insecure-requests` are emitted only when the app is actually
served over https, so the configuration does not claim a protection it is not
providing. `frontend/next.config.test.ts` asserts all of this.

## Machine identities

The worker holds a dedicated `Service Identity` realm role covering exactly the two
operations it performs: the contract expiry roll and the webhook drain. It is
granted to no human and is intentionally **not** a subset of any human role, so
"the worker can do X" and "a person can do X" are independent claims and the
tests check them separately. A leaked worker token is not an administrative token.

A leaked worker secret does grant reach to the tenant the token belongs to. Scope
that by issuing one service account per tenant rather than widening the role.

## Out of scope

Social engineering, physical attacks, third-party SaaS misconfigurations outside Vantor defaults.
