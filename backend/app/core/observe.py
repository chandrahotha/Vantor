"""Request observability — structured access log with request-ID + latency.

Phase 10 will ship OTEL tracing/metrics; until then every request emits one
JSON line (method, path, status, ms, tenant, requestId) to stdout so any log
collector (Docker, CloudWatch, Loki) can aggregate latency/error/tenant stats.
Health probes are excluded to keep the signal clean. No PII logged.
"""
from __future__ import annotations

import json
import sys
import time

from starlette.middleware.base import BaseHTTPMiddleware

SKIP_PATHS = {"/api/v1/health", "/api/v1/ready", "/", "/api/docs", "/api/openapi.json"}


def _is_test() -> bool:
    try:
        from .config import get_settings

        return get_settings().app_env == "test"
    except Exception:
        import os

        return os.getenv("APP_ENV") == "test"


def _tenant_of(request) -> str:  # type: ignore[no-untyped-def]
    state_tenant = getattr(request.state, "tenant_id", "") or ""
    if state_tenant:
        return state_tenant
    # Dependencies (get_actor) run inside the stack — decode here so tenant stats work.
    try:
        from .security import verify_token

        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return verify_token(auth[7:].strip()).tenant_id
    except Exception:
        pass
    return ""


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
        quiet = _is_test()
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            if not quiet and request.url.path not in SKIP_PATHS:
                ms = (time.perf_counter() - start) * 1000
                tenant = _tenant_of(request)
                sys.stdout.write(json.dumps({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "requestId": getattr(request.state, "request_id", ""),
                    "method": request.method, "path": request.url.path,
                    "status": status, "ms": round(ms, 1), "tenant": tenant,
                }) + "\n")
                sys.stdout.flush()
        return response
