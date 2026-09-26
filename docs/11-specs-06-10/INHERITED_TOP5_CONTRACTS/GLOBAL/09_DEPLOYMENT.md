# Deployment Runbook

Local:
install Node/Python → configure env → start DB → migrations → synthetic seed → start frontend/API → tests → browser smoke.

CI:
lint → typecheck → unit → integration → security lint → dependency scan → secret scan → build.

Production:
Vercel frontend + managed API/worker + managed Postgres + object storage + queue + monitoring + WAF/rate limiting.

Separate development/staging/production credentials and databases.

Backup:
PITR where available, versioned object storage, restore tests.

Rollback:
application rollback, migration plan/forward fix, feature flags for risky AI tools.

AI outage:
deterministic results remain available; queue/retry; do not lose source documents.
