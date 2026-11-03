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

echo "==> 6. Checking Frontend Palette Contrast & Token Cycles..."
"$PYTHON" frontend/check_palette_layer.py

echo "==> 7. Checking Documentation Surface Counts..."
"$PYTHON" scripts/doc_counts.py --check

echo "==> 8. Linting Backend with Ruff..."
"$RUFF" check backend/app backend/tests backend/alembic

echo "==> 9. Typechecking Backend with Mypy..."
"$MYPY" backend/app

echo "==> 10. Running Backend Unit Tests (SQLite in-memory)..."
APP_ENV=test DATABASE_URL="sqlite://" OIDC_ISSUER="https://issuer.test/realms/vantor" JWT_AUDIENCE="vantor-web" "$PYTHON" -m pytest backend/tests -q

echo "==> 11. Linting Worker with Ruff..."
"$RUFF" check worker

echo "==> 12. Running Worker Tests..."
"$PYTHON" -m pytest worker/tests -q

echo "==> 13. Typechecking Frontend (tsc)..."
cd "${REPO_ROOT}/frontend"
npm run typecheck

echo "==> 14. Linting Frontend (eslint)..."
npm run lint

echo "==> 15. Running Frontend Tests (vitest)..."
npm test

echo "==> 16. Building Frontend Production Bundle (next build)..."
npm run build

cd "$REPO_ROOT"

echo "==> 17. Checking the Committed OpenAPI Contract Matches the Code..."
# The contract is committed twice (api/openapi.json and api/openapi.yaml) and
# both are regenerated from one `app.openapi()` call, so neither can drift.
# PyYAML renders the YAML copy; without it the JSON is still checked and the
# YAML is reported as unchecked rather than silently passed.
if "$PYTHON" -c "import yaml" >/dev/null 2>&1; then
  "$PYTHON" scripts/generate_openapi.py
  git diff --exit-code -- api/openapi.json api/openapi.yaml || (
    echo "the committed OpenAPI contract is stale - run 'make contract' and commit the result" && exit 1
  )
else
  echo "    PyYAML is not installed - api/openapi.yaml was NOT checked."
  echo "    Install it with: pip install pyyaml==6.0.3"
fi

echo ""
echo "All verification checks passed successfully! Repository is production-ready."
