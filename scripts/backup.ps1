<# Vantor backup / restore — Postgres + uploads + Keycloak realm.
   Usage: .\backup.ps1 / .\restore.ps1 <dump-file>
   Production path is managed PITR; these scripts cover local + small deploys. #>
param([string]$PostgresUser = $env:POSTGRES_USER, [string]$PostgresDb = $env:POSTGRES_DB)

if (-not $PostgresUser) { $PostgresUser = "vantor" }
if (-not $PostgresDb) { $PostgresDb = "vantor" }
$stamp = Get-Date -Format "yyyy-MM-dd"
$out = "backups"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$dump = Join-Path $out "vantor-$stamp.sql"
docker compose exec -T postgres pg_dump -U $PostgresUser $PostgresDb | Set-Content $dump -Encoding UTF8
$hash = (Get-FileHash $dump -Algorithm SHA256).Hash
"$hash  $dump" | Set-Content "$dump.sha256"
Write-Output "backup: $dump ($hash)"
