"""RQ jobs — thin delegates to the API (rules live server-side, never duplicated).

- roll_expiry: POST /api/v1/contracts/roll-expiry (moves active→expiring ≤90d).
- spend_snapshot: GET /api/v1/spend/summary (validates ledgers are queryable).
Auth: service bearer token from SERVICE_API_TOKEN (Keycloak client-credentials
out-of-band). No token => job fails loudly, never anonymous.
"""
from __future__ import annotations

import os

import httpx

TIMEOUT_S = 30.0


def _api() -> str:
    return os.getenv("API_URL", "http://backend:8000").rstrip("/")


def _token() -> str:
    tok = os.getenv("SERVICE_API_TOKEN", "")
    if not tok:
        raise RuntimeError("SERVICE_API_TOKEN missing — refusing anonymous service call")
    return tok


def roll_expiry() -> dict:
    with httpx.Client(timeout=TIMEOUT_S) as c:
        r = c.post(f"{_api()}/api/v1/contracts/roll-expiry", headers={"Authorization": f"Bearer {_token()}"})
        r.raise_for_status()
        return r.json()["data"]


def spend_snapshot() -> dict:
    with httpx.Client(timeout=TIMEOUT_S) as c:
        r = c.get(f"{_api()}/api/v1/spend/summary", headers={"Authorization": f"Bearer {_token()}"})
        r.raise_for_status()
        return r.json()["data"]


JOB_MAP = {"roll_expiry": roll_expiry, "spend_snapshot": spend_snapshot}
