"""Per-tenant rate limiting (Redis fixed-window, fail-open).

Limits (per tenant): 120 mutating req/min, 600 reads/min. Breach => 429 with the
standard error envelope + Retry-After. Redis outage => fail-open (allow + header
mark) so the limiter can never take down procurement; outages surface via /ready.
Only the limiter's own errors are swallowed — never application errors.
"""
from __future__ import annotations

import os
import time

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

WRITE_LIMIT = int(os.getenv("RATE_LIMIT_WRITE_PER_MIN", "120"))
READ_LIMIT = int(os.getenv("RATE_LIMIT_READ_PER_MIN", "600"))
WINDOW_S = 60

_client = None


def _redis():  # type: ignore[no-untyped-def]
    global _client
    if _client is None:
        try:
            from redis import Redis as _R

            from .config import get_settings

            _client = _R.from_url(get_settings().redis_url, socket_timeout=0.5)
            _client.ping()
        except Exception:
            _client = False
    return _client or None


def reset_limiter_cache() -> None:
    global _client
    _client = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path in {"/api/v1/health", "/api/v1/ready", "/api/docs", "/api/openapi.json", "/"}:
            return await call_next(request)
        tenant = ""
        try:
            from .security import verify_token

            auth = request.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                tenant = verify_token(auth[7:].strip()).tenant_id
        except Exception:
            return await call_next(request)  # auth failures handled downstream (401)
        if not tenant:
            return await call_next(request)
        limit = WRITE_LIMIT if request.method in {"POST", "PUT", "PATCH", "DELETE"} else READ_LIMIT
        r = _redis()
        if r is None:
            resp = await call_next(request)
            resp.headers["X-RateLimit-Bypass"] = "limiter-unavailable"
            return resp
        bucket = int(time.time() // WINDOW_S)
        key = f"rl:{tenant}:{request.method}:{bucket}"
        try:
            n = r.incr(key)
            if n == 1:
                r.expire(key, WINDOW_S + 5)
        except Exception:
            resp = await call_next(request)
            resp.headers["X-RateLimit-Bypass"] = "limiter-error"
            return resp
        if n > limit:
            return JSONResponse(status_code=429, content={
                "data": None, "pagination": None,
                "error": {"code": "RATE_LIMITED", "message": f"Too many requests ({limit}/min)", "details": {}},
                "requestId": getattr(request.state, "request_id", "")},
                headers={"Retry-After": str(WINDOW_S)})
        resp = await call_next(request)
        resp.headers["X-RateLimit-Remaining"] = str(max(0, limit - n))
        return resp
