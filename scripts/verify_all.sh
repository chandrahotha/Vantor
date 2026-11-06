#!/usr/bin/env bash
# Complete local verification script for Vantor (Bash)
# Runs the full verification pipeline: code hygiene, types, lint, tests, and production builds.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${REPO_ROOT}/backend/.venv/bin/python"
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

RUFF="${REPO_ROOT}/backend/.venv/bin/ruff"
if [ ! -f "$RUFF" ]; then
    RUFF="ruff"
fi

MYPY="${REPO_ROOT}/backend/.venv/bin/mypy"
if [ ! -f "$MYPY" ]; then
    MYPY="mypy"
fi

echo "==> 1. Running Secret Guard..."
"$PYTHON" scripts/check_secrets.py

echo "==> 2. Checking File Encodings..."
"$PYTHON" scripts/check_mojibake.py

echo "==> 3. Verifying Documentation Links..."
"$PYTHON" scripts/verify_doc_links.py

echo "==> 4. Auditing Migration Linearity..."
"$PYTHON" scripts/audit_migrations.py

echo "==> 5. Verifying Pinned Container Digests..."
"$PYTHON" scripts/pin_digests.py --check

echo "==> 6. Verifying CI Gates Can Still Fail..."
"$PYTHON" scripts/check_ci_consistency.py --check

echo "==> 7. Checking Frontend Palette Contrast & Token Cycles..."
"$PYTHON" frontend/check_palette_layer.py

echo "==> 8. Checking Documentation Surface Counts..."
"$PYTHON" scripts/doc_counts.py --check

echo "==> 9. Linting Backend with Ruff..."
"$RUFF" check backend/app backend/tests backend/alembic

echo "==> 10. Typechecking Backend with Mypy..."
"$MYPY" backend/app

echo "==> 11. Running Backend Unit Tests (SQLite in-memory)..."
APP_ENV=test DATABASE_URL="sqlite://" OIDC_ISSUER="https://issuer.test/realms/vantor" JWT_AUDIENCE="vantor-web" "$PYTHON" -m pytest backend/tests -q

echo "==> 12. Linting Worker with Ruff..."
"$RUFF" check worker

echo "==> 13. Running Worker Tests..."
"$PYTHON" -m pytest worker/tests -q

echo "==> 14. Typechecking Frontend (tsc)..."
cd "${REPO_ROOT}/frontend"
npm run typecheck

echo "==> 15. Linting Frontend (eslint)..."
npm run lint

echo "==> 16. Running Frontend Tests (vitest)..."
npm test

echo "==> 17. Building Frontend Production Bundle (next build)..."
npm run build

cd "$REPO_ROOT"

echo "==> 18. Checking the Committed OpenAPI Contract Matches the Code..."
# The contract is committed twice (api/openapi.json and api/openapi.yaml) and
# both are regenerated from one `app.openapi()` call, so neither can drift.
# PyYAML renders the YAML copy. It is pinned in backend/requirements.txt, so a
# missing module here is a broken environment, not an optional extra: the old
# version printed "was NOT checked" and exited 0, which let a stale contract
# through on any machine that had not installed it.
if ! "$PYTHON" -c "import yaml" >/dev/null 2>&1; then
    echo "FAIL: PyYAML is not installed, so api/openapi.yaml cannot be checked."
    echo "      It is pinned in backend/requirements.txt — install it with:"
    echo "        $PYTHON -m pip install pyyaml==6.0.3"
    exit 1
fi
"$PYTHON" scripts/generate_openapi.py
git diff --exit-code -- api/openapi.json api/openapi.yaml || (
    echo "the committed OpenAPI contract is stale - run 'make contract' and commit the result" && exit 1
)

echo ""
echo "All local gates passed."
echo ""
echo "What this run did NOT cover, and therefore does not certify:"
echo "  - PostgreSQL tier (RLS, foreign keys, concurrency): needs PG_TEST_DATABASE_URL"
echo "  - the Alembic upgrade/check/downgrade drill on a real database"
echo "  - Playwright end-to-end flows and the axe accessibility run"
echo "  - dependency audits (pip-audit, npm audit) and the container image builds"
echo "  - the Compose stack actually booting, or the single-container image serving a browser"
echo "Those run in CI (weekly, or \`full_suite: true\`). See docs/00-plan/ROADMAP.md Phase 10:"
echo "the production-hardening gate is NOT MET, and a clean run of this script is not a"
echo "statement that the repository is production-ready."
