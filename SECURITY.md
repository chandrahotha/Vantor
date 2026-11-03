# Security Policy - VANTOR

> Documentation index: [docs/README.md](docs/README.md)

The controls under **Enforced in the code** are implemented and covered by the
automated suite. The ones under **Your responsibility** are deployment
choices VANTOR cannot make for you. Anything not listed in either section is
not claimed.

## Supported versions

| Version | Supported |
|---|---|
| `main` | Best effort - this is a pre-`1.0` project; see `CHANGELOG.md` for what has shipped |
| Future `1.x` releases | Security patches documented in CHANGELOG |

## Reporting a vulnerability

- **Do not open a public issue for vulnerabilities.**
- Email privately: **digi.tracks@outlook.com** (Digi Tracks).
- Include: affected version/commit, reproduction steps, impact, suggested mitigation.
- Expect acknowledgement within 72 hours. There is no dedicated security team or SLA
  behind this project today - triage timing is best-effort until that changes.

## Enforced in the code

- **Two auth modes, one verification path.** `AUTH_MODE=local` (default) makes
  the API its own issuer — RS256 tokens, no identity service, but
  **passwordless**: anyone who can reach the deployment is the operator, so
  this mode is for single-container, SQLite, single-operator use only.
  `AUTH_MODE=oidc` requires Keycloak, with short-lived JWTs and rotating
  refresh tokens. Both modes verify the same way: a forged or foreign-signed
  token is a 401 either way.
- **RBAC and resource-level authorisation** on every endpoint, with
  `tenant_id` row-level security on every query in PostgreSQL. The RLS
  backstop fails closed.
- **Machine identities are least-privilege by construction** — see
  [Machine identities](#machine-identities) below.
- **Tenant-scoped data paths.** Search, storage, logs and AI context are all
  tenant-scoped, and cross-tenant isolation is covered by the test suite.
- **Validated uploads.** Magic-byte sniffing against the declared type, an
  extension allowlist, and a size ceiling enforced before and during the
  read.
- **Rate limiting**, per route and per identity, with separate read and write
  budgets.
- **CORS is an explicit allowlist, and it fails closed.** Only origins on the
  list — `APP_URL`, `API_URL`, and the local development origins outside
  production — receive a grant; every other origin gets none. The grant is
  applied to error responses as well as successful ones, so a cross-origin
  client can read an API error instead of seeing an opaque network failure.
  If you serve the web app from an origin that is not on the list, add it to
  `APP_URL`; a request from an unlisted origin is refused, not redirected.
- **Security headers** on both the API and the web app — see the
  [Content-Security-Policy](#where-the-content-security-policy-actually-applies)
  section below.
- **Immutable audit log** for every significant action, including AI tool
  calls. Entries are hash-chained.
- **Idempotent mutations.** Workflow actions accept an idempotency key, and a
  replayed request cannot apply twice.
- **AI is treated as an untrusted-input boundary.** Typed tools only — no raw
  SQL, no shell — with prompt-injection defences and evidence requirements
  ([AI safety](docs/03-ai/safety.md)).
- **Dependency and supply-chain checks in CI**
  ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): `pip-audit` and
  `npm audit` on every push, plus a secret scan, a container digest check and
  a migration-chain check.
- **Every container image is pinned by digest** — the compose stack, the CI
  service containers, and the base images the Dockerfiles build from. A tag
  is a mutable name, so a pinned image is the same bytes today and tomorrow.
  The check is offline and runs on every push; it fails on an unpinned or
  malformed digest.
- **The images the project ships are built by CI.** A Dockerfile that no
  longer parses, a base image that no longer resolves, or a requirements file
  that cannot be installed fails the build rather than reaching a release.

## Not implemented

Stated plainly so nobody relies on them:

- **No malware scanning.** Uploads are validated by type and size, not
  scanned. Put a scanner in front of the storage path if you need one.
- **No OCR.** A scanned document with no text layer is quarantined, not
  processed. There is no OCR sandbox to isolate.
- **No CSRF tokens.** Authentication is a bearer token in an `Authorization`
  header, not a cookie, so there is no cookie-authenticated endpoint for a
  CSRF token to protect. If you add cookie authentication, add CSRF
  protection with it.
- **The filesystem storage driver is the default.** Object storage is
  available via `STORAGE_DRIVER=s3` and the `S3_*` variables, but the
  default local stack writes to disk.

## Your responsibility

- **TLS.** VANTOR terminates plain HTTP. Put it behind a TLS-terminating
  proxy and set `APP_URL`/`API_URL` to the `https://` origins.
- **Encryption at rest** is a property of your disk or managed database.
- **Secrets.** Use a secret manager. `.env` is a development convenience and
  must never be committed.
- **Database credentials.** The application role is separate from the schema
  owner so that RLS applies to the application's own queries.
- **Single-operator mode is not multi-user.** `AUTH_MODE=local` has no
  concept of users. Use `oidc` for anything shared.

## Where the Content-Security-Policy actually applies

A CSP delivered by one origin does **not** apply to documents served by another.
VANTOR runs the API and the web app on separate origins, and the pages a user
actually reads are served by Next - so the API's policy, however strict, was
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
`NEXT_PUBLIC_KEYCLOAK_URL`, not hardcoded - a pinned `localhost:8000` would have
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
