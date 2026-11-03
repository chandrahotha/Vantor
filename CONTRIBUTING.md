# Contributing to VANTOR

> Documentation index: [docs/README.md](docs/README.md)

## Ground rules

1. Do not claim a capability that is not implemented and tested. If it is
   half-built, say which half.
2. No mocks presented as real: no fake dashboards, fake AI, hard-coded
   suppliers, UI-only CRUD.
3. If an integration needs credentials you lack, implement a clean interface
   and document the required configuration. Never fake it as operational.
4. Every PR: format + lint + typecheck + tests + security/dependency scan +
   migration check.
5. Record tradeoffs in `docs/10-decisions/ADR-*.md`. Document assumptions when
   requirements are ambiguous.

## Workflow

```powershell
git checkout -b feat/<scope>-<short-desc>
Copy-Item .env.example .env
python scripts/pin_digests.py       # resolves real image digests into .env; required once before compose
docker compose up -d postgres redis keycloak ollama
python -m pytest backend/tests -q   # backend
cd frontend; npm run typecheck; npm run lint; npm test; cd ..
git commit -m "feat(scope): what + why"
gh pr create --fill
```

Object storage is BYO S3-compatible (`S3_ENDPOINT`/`S3_BUCKET` in `.env`) or local-disk
in development; there is no bundled MinIO service.

### Images are pinned by digest

Every container image the project runs — the compose stack and the CI service
containers alike — is pinned to a digest rather than a tag. A tag is a mutable
name: `redis:7-alpine` can point at different bytes tomorrow, so a rebuilt
upstream tag silently changes what was tested.

`python scripts/pin_digests.py --check` is the gate. It is offline and runs on
every push:

- the **compose** images are pinned through `.env` indirection, so a developer
  can override them without editing the compose file;
- the **CI** images are pinned inline in `.github/workflows/ci.yml`, because a
  CI job has no `.env` and the workflow is what names the image.

Refresh the compose digests with `python scripts/pin_digests.py` (network
access required). The CI digests are literals in the workflow — update them by
hand when an image needs to move, and the `--check` gate will tell you if you
forget.

## The tiers CI runs

| Tier | When | What it needs |
|---|---|---|
| Fast | every push and pull request | nothing — SQLite in memory, no Redis, no Postgres |
| Worker | every push and pull request | a Redis service (now provided by CI) |
| Postgres | weekly schedule, and `workflow_dispatch` with `full_suite: true` | a real PostgreSQL — set `PG_TEST_DATABASE_URL` |
| End-to-end | weekly schedule, and `workflow_dispatch` with `full_suite: true` | a running API on port 8000 and Playwright's chromium |

Run the Postgres tier locally against any PostgreSQL:

```bash
PG_TEST_DATABASE_URL="postgresql://user:pass@localhost:5432/vantor_test" \
APP_DB_PASSWORD="..." python -m pytest backend/tests -m pg -q
```

Run the end-to-end tier locally:

```bash
cd backend && AUTH_MODE=local DATABASE_URL="sqlite:///./data/e2e.db" python -m uvicorn app.main:app --port 8000 &
cd frontend && npm ci && npx playwright install chromium && npx playwright test
```

The API's CORS allowlist is derived from `APP_URL`, so if you serve the web app
on a port other than 3000, set `APP_URL` to match it (`E2E_PORT=3100` moves the
Playwright server to 3100). Without that, the browser refuses the API's
responses and the suite reports a CORS failure rather than a product one.

## The OpenAPI contract

`api/openapi.json` and `api/openapi.yaml` are generated from the application —
one `app.openapi()` call writes both, so they cannot disagree with each other.
After changing a request or response model:

```bash
make contract          # or: python scripts/generate_openapi.py
git add api/openapi.json api/openapi.yaml
```

CI regenerates both and fails the build if either drifts. The YAML copy needs
PyYAML (`make install` installs it); the JSON copy does not.

## PR checklist

- [ ] Domain model + migration + backend + authz + frontend + validation + errors + audit + tests + docs updated as appropriate
- [ ] Tenant isolation covered for new data paths
- [ ] AI changes include eval regression + evidence citations
- [ ] No secrets committed (`.env`, keys, tokens)

## Code style

- Backend: typed schemas, versioned REST (`/api/v1`), consistent error envelope, pagination/filter/sort.
- Frontend: Vantor design tokens only (`docs/05-frontend/design-system.md`), accessible tables/dialogs/forms, skeletons for async states.
