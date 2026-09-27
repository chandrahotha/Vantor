"""RQ jobs — thin delegates to the API (rules live server-side, never duplicated).

- `roll_expiry`    POST /api/v1/contracts/roll-expiry (moves active -> expiring <=90d)
- `spend_snapshot` GET  /api/v1/spend/summary        (validates ledgers are queryable)
- `drain_webhooks` POST /api/v1/webhooks/drain        (VNT-008 durable delivery queue)

VNT-044. Authentication used to be a single hand-pasted `SERVICE_API_TOKEN` that
a human had to mint out of band and paste into `.env`. That has three problems:
the token expires and nothing noticed, so a scheduled job began failing
permanently; the worker could not rotate it; and nothing in the repository
bootstrapped the identity it needed.

The worker now performs a Keycloak **client-credentials** grant itself, caches the
access token until shortly before it expires, and refreshes on demand. The
service client is created by the realm bootstrap (`deploy/keycloak/realm.json`,
imported by compose), so `docker compose up` yields a working identity rather
than a missing one. `SERVICE_API_TOKEN` is still honoured as an escape hatch for
environments where the grant is unavailable, but it is no longer the only path
and no longer the documented one.
"""
from __future__ import annotations

import os
import time

import httpx

TIMEOUT_S = 30.0
AUTH_TIMEOUT_S = 10.0

#: Refresh this many seconds before the token actually expires, so a job that
#: starts just before expiry does not carry a dead token into its call.
TOKEN_REFRESH_MARGIN_S = 60.0

_token_cache: dict[str, object] = {"value": "", "expires_at": 0.0}


def _api() -> str:
    return os.getenv("API_URL", "http://backend:8000").rstrip("/")


def _issuer() -> str:
    issuer = os.getenv("OIDC_ISSUER", "").strip()
    if not issuer:
        raise RuntimeError("OIDC_ISSUER is not set — cannot obtain a service token")
    return issuer.rstrip("/")


def _fetch_client_credentials_token() -> str:
    """Exchange the service client's secret for an access token.

    Fails loudly. An anonymous service call is never acceptable, so there is no
    fallback to "no auth" anywhere in this function.
    """
    client_id = os.getenv("SERVICE_CLIENT_ID", "").strip()
    client_secret = os.getenv("SERVICE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "SERVICE_CLIENT_ID / SERVICE_CLIENT_SECRET are required for the "
            "client-credentials grant; refusing anonymous service call")
    token_url = f"{_issuer()}/protocol/openid-connect/token"
    form = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    # A confidential client may authenticate with HTTP Basic instead; try the
    # form body first and fall back, because Keycloak accepts both and the realm
    # decides which is enabled.
    with httpx.Client(timeout=AUTH_TIMEOUT_S) as c:
        response = c.post(token_url, data=form)
        if response.status_code >= 400:
            response = c.post(token_url, data=form, auth=(client_id, client_secret))
        response.raise_for_status()
    body = response.json()
    token = body.get("access_token", "")
    if not token:
        raise RuntimeError(f"token endpoint returned no access_token (keys: {sorted(body)})")
    expires_in = float(body.get("expires_in", 60) or 60)
    _token_cache["value"] = token
    _token_cache["expires_at"] = time.monotonic() + max(
        0.0, expires_in - TOKEN_REFRESH_MARGIN_S)
    return token


def _token() -> str:
    """A valid service bearer token, refreshed before it expires.

    Cache is process-local and in-memory, so a restart simply re-authenticates.
    """
    cached = _token_cache.get("value") or ""
    if cached and time.monotonic() < float(_token_cache.get("expires_at") or 0.0):
        return str(cached)

    static = os.getenv("SERVICE_API_TOKEN", "").strip()
    if static:
        return static
    return _fetch_client_credentials_token()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}"}


def _call(method: str, path: str) -> dict:
    with httpx.Client(timeout=TIMEOUT_S) as c:
        r = c.request(method, f"{_api()}{path}", headers=_auth_headers())
        r.raise_for_status()
        return r.json().get("data", {})


def roll_expiry() -> dict:
    return _call("POST", "/api/v1/contracts/roll-expiry")


def spend_snapshot() -> dict:
    return _call("GET", "/api/v1/spend/summary")


def drain_webhooks(limit: int = 50) -> dict:
    """Attempt every due webhook delivery.

    VNT-008. The queue is durable and the retry schedule lives in the database,
    so this job is a plain "is anything due?" tick. It needs no local state, which
    means a worker restart loses nothing and two workers do not double-send.
    """
    return _call("POST", f"/api/v1/webhooks/drain?limit={int(limit)}")


def sweep_idempotency_claims() -> dict:
    """Housekeeping hook. Kept as an explicit job so the schedule is visible."""
    return {"skipped": "no-op; claim expiry is enforced inline by the middleware"}


JOB_MAP = {
    "roll_expiry": roll_expiry,
    "spend_snapshot": spend_snapshot,
    "drain_webhooks": drain_webhooks,
    "sweep_idempotency_claims": sweep_idempotency_claims,
}
