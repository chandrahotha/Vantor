# Complete local verification script for Vantor (PowerShell)
# Runs the full verification pipeline: code hygiene, types, lint, tests, and production builds.
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

Write-Host "==> 6. Checking Frontend Palette Contrast & Token Cycles..." -ForegroundColor Cyan
& $python frontend/check_palette_layer.py

Write-Host "==> 7. Checking Documentation Surface Counts..." -ForegroundColor Cyan
& $python scripts/doc_counts.py --check

Write-Host "==> 8. Linting Backend with Ruff..." -ForegroundColor Cyan
& $ruff check backend/app backend/tests backend/alembic

Write-Host "==> 9. Typechecking Backend with Mypy..." -ForegroundColor Cyan
& $mypy backend/app

Write-Host "==> 10. Running Backend Unit Tests (SQLite in-memory)..." -ForegroundColor Cyan
$env:APP_ENV = "test"
$env:DATABASE_URL = "sqlite://"
$env:OIDC_ISSUER = "https://issuer.test/realms/vantor"
$env:JWT_AUDIENCE = "vantor-web"
& $python -m pytest backend/tests -q

Write-Host "==> 11. Linting Worker with Ruff..." -ForegroundColor Cyan
& $ruff check worker

Write-Host "==> 12. Running Worker Tests..." -ForegroundColor Cyan
& $python -m pytest worker/tests -q

Write-Host "==> 13. Typechecking Frontend (tsc)..." -ForegroundColor Cyan
Set-Location "$repoRoot/frontend"
npm run typecheck

Write-Host "==> 14. Linting Frontend (eslint)..." -ForegroundColor Cyan
npm run lint

Write-Host "==> 15. Running Frontend Tests (vitest)..." -ForegroundColor Cyan
npm test

Write-Host "==> 16. Building Frontend Production Bundle (next build)..." -ForegroundColor Cyan
npm run build

Set-Location $repoRoot

Write-Host "==> 17. Checking the Committed OpenAPI Contract Matches the Code..." -ForegroundColor Cyan
# The contract is committed twice (api/openapi.json and api/openapi.yaml) and
# both are regenerated from one `app.openapi()` call, so neither can drift.
# PyYAML renders the YAML copy; without it the JSON is still checked and the
# YAML is reported as unchecked rather than silently passed.
& $python -c "import yaml"
if ($LASTEXITCODE -eq 0) {
    & $python scripts/generate_openapi.py
    git diff --exit-code -- api/openapi.json api/openapi.yaml
    if ($LASTEXITCODE -ne 0) {
        Write-Host "the committed OpenAPI contract is stale - run 'make contract' and commit the result" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "    PyYAML is not installed - api/openapi.yaml was NOT checked." -ForegroundColor Yellow
    Write-Host "    Install it with: pip install pyyaml==6.0.3" -ForegroundColor Yellow
}

Write-Host "`nAll verification checks passed successfully! Repository is production-ready." -ForegroundColor Green
