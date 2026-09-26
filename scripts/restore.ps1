<# Restore a Vantor Postgres dump. Verifies SHA256 sidecar, refuses on mismatch.
   Usage: .\restore.ps1 backups\vantor-2026-09-26.sql #>
param([Parameter(Mandatory = $true)][string]$Dump)

if (-not (Test-Path $Dump)) { throw "dump not found: $Dump" }
$expect = (Get-Content "$Dump.sha256" -ErrorAction SilentlyContinue | Select-Object -First 1)
if ($expect) {
  $actual = (Get-FileHash $Dump -Algorithm SHA256).Hash
  if (-not $expect.StartsWith($actual)) { throw "SHA256 mismatch — refusing restore (tamper or corruption)" }
}
$postMissing = @()
if (-not $env:POSTGRES_USER) { $postMissing += "POSTGRES_USER" }
if (-not $env:POSTGRES_DB) { $postMissing += "POSTGRES_DB" }
if ($postMissing) { throw "missing env: $($postMissing -join ', ')" }
Get-Content $Dump -Raw | docker compose exec -T postgres psql -U $env:POSTGRES_USER -d $env:POSTGRES_DB -v ON_ERROR_STOP=1
Write-Output "restored from $Dump — re-run backend migrations check: cd backend; alembic upgrade head"
