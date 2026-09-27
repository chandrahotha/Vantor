#!/bin/sh
# Provision the VANTOR Keycloak realm over the admin API. Runs once, then exits.
#
# VNT-036. `docker compose up` previously produced a Keycloak with no realm, no
# client and no roles, so the documented quickstart could not issue a token.
#
# The realm *shape* is imported by Keycloak itself (--import-realm). Everything
# that needs the service client's secret cannot be, because --import-realm reads
# a static file. This reconciles those parts through the admin API, on every
# start, which is also what makes secret rotation work.

set -eu

: "${KEYCLOAK_ADMIN_PASSWORD:?KEYCLOAK_ADMIN_PASSWORD must be set}"
: "${SERVICE_CLIENT_SECRET:?SERVICE_CLIENT_SECRET must be set}"

# Retries live here rather than relying only on the compose healthcheck: a
# dependent service must not trust that a healthcheck was ever evaluated, and a
# Keycloak that was already running skips its own health history on restart.
attempt=0
until python /app/provision.py; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 5 ]; then
    echo "keycloak provisioning failed after ${attempt} attempts" >&2
    exit 1
  fi
  echo "retrying provisioning (${attempt}/5) in 10s" >&2
  sleep 10
done

echo "realm provisioning finished"
