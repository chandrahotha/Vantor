#!/bin/bash
# Start the API and the web server, and die together.
#
# bash, not sh: `wait -n` (exit as soon as *either* child does) is a bash
# builtin, and on Debian /bin/sh is dash, where it is not reliably available.
#
# No supervisor and no init system: two processes, and if either one exits the
# container exits. A container that keeps running with half the product dead is
# worse than one that restarts — the platform's own restart policy and the
# healthcheck can only help if failure is visible.
set -eu

API_PORT="${API_PORT:-8000}"
PORT="${PORT:-8080}"

mkdir -p /data/uploads

echo "vantor: starting API on 127.0.0.1:${API_PORT}"
python -m uvicorn app.main:app \
  --app-dir /srv/backend \
  --host 127.0.0.1 \
  --port "${API_PORT}" \
  --log-level "${LOG_LEVEL:-info}" &
API_PID=$!

# The web server proxies /api to the API, so it must not start answering before
# the API can respond or the first page load races it and renders its error
# state. Bounded: if the API cannot come up, fail loudly rather than serve a
# broken app forever.
i=0
until python - <<'PY' 2>/dev/null
import os, sys, urllib.request
url = f"http://127.0.0.1:{os.environ.get('API_PORT', '8000')}/api/v1/health"
sys.exit(0 if urllib.request.urlopen(url, timeout=2).status == 200 else 1)
PY
do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "vantor: API did not become healthy in 60s" >&2
    kill "$API_PID" 2>/dev/null || true
    exit 1
  fi
  # Has the API already died? Then there is nothing to wait for.
  kill -0 "$API_PID" 2>/dev/null || { echo "vantor: API exited during startup" >&2; exit 1; }
  sleep 1
done
echo "vantor: API healthy"

echo "vantor: starting web on 0.0.0.0:${PORT}"
INTERNAL_API_URL="http://127.0.0.1:${API_PORT}" \
HOSTNAME=0.0.0.0 \
PORT="${PORT}" \
  node /srv/web/server.js &
WEB_PID=$!

# Forward a stop signal to both, so `docker stop` is a clean shutdown rather
# than a ten-second wait and a SIGKILL.
trap 'kill -TERM "$API_PID" "$WEB_PID" 2>/dev/null || true' TERM INT

# Exit as soon as either child does, carrying its status.
wait -n "$API_PID" "$WEB_PID"
STATUS=$?
echo "vantor: a process exited (status ${STATUS}); shutting down"
kill -TERM "$API_PID" "$WEB_PID" 2>/dev/null || true
wait 2>/dev/null || true
exit "$STATUS"
