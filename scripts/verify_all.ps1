# Complete local verification script for Vantor (PowerShell)
# Runs the full verification pipeline: code hygiene, types, lint, tests, and production builds.
#
# This file and scripts/verify_all.sh are the same pipeline in two languages.
# `check_ci_consistency.py` cannot prove they agree, so the step numbers and the
# closing caveat are kept identical by hand — a divergence here means a developer
# on one platform passed a gate the other platform never ran.
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$python = if (Test-Path "$repoRoot/backend/.venv/Scripts/python.exe") {
    "$repoRoot/backend/.venv/Scripts/python.exe"
} else {
    "python"
}

$ruff = if (Test-Path "$repoRoot/backend/.venv/Scripts/ruff.exe") {
    "$repoRoot/backend/.venv/Scripts/ruff.exe"
} else {
    "ruff"
}

$mypy = if (Test-Path "$repoRoot/backend/.venv/Scripts/mypy.exe") {
    "$repoRoot/backend/.venv/Scripts/mypy.exe"
} else {
    "mypy"
}

Write-Host "==> 1. Running Secret Guard..." -ForegroundColor Cyan
& $python scripts/check_secrets.py

Write-Host "==> 2. Checking File Encodings..." -ForegroundColor Cyan
& $python scripts/check_mojibake.py

Write-Host "==> 3. Verifying Documentation Links..." -ForegroundColor Cyan
& $python scripts/verify_doc_links.py

Write-Host "==> 4. Auditing Migration Linearity..." -ForegroundColor Cyan
& $python scripts/audit_migrations.py

Write-Host "==> 5. Verifying Pinned Container Digests..." -ForegroundColor Cyan
& $python scripts/pin_digests.py --check

Write-Host "==> 6. Verifying CI Gates Can Still Fail..." -ForegroundColor Cyan
& $python scripts/check_ci_consistency.py --check

Write-Host "==> 7. Checking Frontend Palette Contrast & Token Cycles..." -ForegroundColor Cyan
& $python frontend/check_palette_layer.py

Write-Host "==> 8. Checking Documentation Surface Counts..." -ForegroundColor Cyan
& $python scripts/doc_counts.py --check

Write-Host "==> 9. Linting Backend with Ruff..." -ForegroundColor Cyan
& $ruff check backend/app backend/tests backend/alembic

Write-Host "==> 10. Typechecking Backend with Mypy..." -ForegroundColor Cyan
& $mypy backend/app

Write-Host "==> 11. Running Backend Unit Tests (SQLite in-memory)..." -ForegroundColor Cyan
$env:APP_ENV = "test"
$env:DATABASE_URL = "sqlite://"
$env:OIDC_ISSUER = "https://issuer.test/realms/vantor"
$env:JWT_AUDIENCE = "vantor-web"
& $python -m pytest backend/tests -q

Write-Host "==> 12. Linting Worker with Ruff..." -ForegroundColor Cyan
& $ruff check worker

Write-Host "==> 13. Running Worker Tests..." -ForegroundColor Cyan
& $python -m pytest worker/tests -q

Write-Host "==> 14. Typechecking Frontend (tsc)..." -ForegroundColor Cyan
Set-Location "$repoRoot/frontend"
npm run typecheck

Write-Host "==> 15. Linting Frontend (eslint)..." -ForegroundColor Cyan
npm run lint

Write-Host "==> 16. Running Frontend Tests (vitest)..." -ForegroundColor Cyan
npm test

Write-Host "==> 17. Building Frontend Production Bundle (next build)..." -ForegroundColor Cyan
npm run build

Set-Location $repoRoot

Write-Host "==> 18. Checking the Committed OpenAPI Contract Matches the Code..." -ForegroundColor Cyan
# The contract is committed twice (api/openapi.json and api/openapi.yaml) and
# both are regenerated from one `app.openapi()` call, so neither can drift.
# PyYAML renders the YAML copy. It is pinned in backend/requirements.txt, so a
# missing module here is a broken environment, not an optional extra: the old
# version printed "was NOT checked" and passed, which let a stale contract
# through on any machine that had not installed it.
& $python -c "import yaml" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: PyYAML is not installed, so api/openapi.yaml cannot be checked." -ForegroundColor Red
    Write-Host "      It is pinned in backend/requirements.txt - install it with:" -ForegroundColor Red
    Write-Host "        & $python -m pip install pyyaml==6.0.3" -ForegroundColor Red
    exit 1
}
& $python scripts/generate_openapi.py
git diff --exit-code -- api/openapi.json api/openapi.yaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "the committed OpenAPI contract is stale - run 'make contract' and commit the result" -ForegroundColor Red
    exit 1
}

Write-Host "`nAll local gates passed." -ForegroundColor Green
Write-Host ""
Write-Host "What this run did NOT cover, and therefore does not certify:"
Write-Host "  - PostgreSQL tier (RLS, foreign keys, concurrency): needs PG_TEST_DATABASE_URL"
Write-Host "  - the Alembic upgrade/check/downgrade drill on a real database"
Write-Host "  - Playwright end-to-end flows and the axe accessibility run"
Write-Host "  - dependency audits (pip-audit, npm audit) and the container image builds"
Write-Host "  - the Compose stack actually booting, or the single-container image serving a browser"
Write-Host "Those run in CI (weekly, or 'full_suite: true'). See docs/00-plan/ROADMAP.md Phase 10:"
Write-Host "the production-hardening gate is NOT MET, and a clean run of this script is not a"
Write-Host "statement that the repository is production-ready."
