<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../docs/BRAIN.md) · [Docs index](../docs/README.md)

## Description
A concise summary of the changes made, the rationale, and the specific subsystem affected.

## Related Issues
Closes #(issue) / Fixes #(issue)

## Subsystem
- [ ] Backend API (`backend/app/`)
- [ ] Database Migrations / RLS (`backend/alembic/`)
- [ ] Frontend Web App (`frontend/app/`, `frontend/components/`)
- [ ] Background Worker (`worker/`)
- [ ] Deploy / Keycloak / Docker (`deploy/`, `docker-compose.yml`)
- [ ] Documentation / Specifications (`docs/`)

## Verification Checklist
- [ ] Tested locally: unit tests passing (`pytest backend/tests -q`, `npm test`)
- [ ] Type checking clean: `mypy backend/app` and `npm run typecheck`
- [ ] Linting clean: `ruff check backend worker` and `npm run lint`
- [ ] Secret guard clean: `python scripts/check_secrets.py`
- [ ] Documentation counts verified: `python scripts/doc_counts.py --check`
- [ ] Tenant isolation verified: no unpinned sessions or cross-tenant leakage
- [ ] No fake data, no unauthenticated bypasses, no secrets committed in `.env`
