<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](docs/BRAIN.md) · [Docs index](docs/README.md)

# Contributing to VANTOR

## Ground rules

1. Never claim `PRODUCTION READY` unless Definition of Done is met (see `docs/00-plan/ROADMAP.md`).
2. No mocks presented as real: no fake dashboards, fake AI, hard-coded suppliers, UI-only CRUD.
3. If an integration needs credentials you lack, implement a clean interface + document required config. Never fake it as operational.
4. Every PR: format + lint + typecheck + tests + security/dependency scan + migration check.
5. Record tradeoffs in `docs/10-decisions/ADR-*.md`. Document assumptions when requirements are ambiguous.

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

## PR checklist

- [ ] Domain model + migration + backend + authz + frontend + validation + errors + audit + tests + docs updated as appropriate
- [ ] Tenant isolation covered for new data paths
- [ ] AI changes include eval regression + evidence citations
- [ ] No secrets committed (`.env`, keys, tokens)

## Code style

- Backend: typed schemas, versioned REST (`/api/v1`), consistent error envelope, pagination/filter/sort.
- Frontend: Vantor design tokens only (`docs/05-frontend/design-system.md`), accessible tables/dialogs/forms, skeletons for async states.
