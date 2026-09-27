# Current Technical Stack

## Authoritative manifests

- `backend/requirements.txt`
- `frontend/package.json`
- `frontend/package-lock.json`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `worker/Dockerfile`
- `docker-compose.yml`
- `.env.example`

## Source-of-truth rule

Do not blindly downgrade or upgrade dependencies because documentation is stale. Before dependency changes:

- inspect current lockfiles;
- read changelogs/release notes for breaking changes;
- run the full test/build suite;
- update compatibility documentation;
- pin production artifacts immutably.

## Target production posture

Use supported stable versions after a deliberate upgrade review. Do not treat the current versions as a permanent target merely because they are present today.
