"""Request observability — structured access log + in-process metrics.

Every request emits one JSON line (method, path, status, ms, tenant, requestId)
so any log collector can aggregate. In-process counters power `GET /api/v1/ops/
metrics` (admin-only) so ops can read *this* process without a Prometheus
exporter. OTEL tracing is a Phase 10 follow-up; this is the honest baseline.

Health probes are excluded to keep the signal clean. No PII logged.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware

SKIP_PATHS = {"/api/v1/health", "/api/v1/ready", "/", "/api/docs", "/api/openapi.json", "/api/v1/ops/metrics"}

_lock = threading.Lock()
_counters = {"requests": 0, "errors5xx": 0, "errors4xx": 0}
_latencies: deque = deque(maxlen=4096)
_start = time.perf_counter()


def _record(status: int, ms: float) -> None:
    with _lock:
        _counters["requests"] += 1
        if status >= 500:
            _counters["errors5xx"] += 1
        elif status >= 400:
            _counters["errors4xx"] += 1
        _latencies.append(ms)


def metrics_snapshot() -> dict:
    with _lock:
        lat = sorted(_latencies)
        p95 = lat[int(len(lat) * 0.95) - 1] if lat else 0.0
        top = list(_counters.items())
    return {
        "process": {"uptimeSeconds": round(time.perf_counter() - _start, 1)},
        "requests": dict(top),
        "latency": {"count": len(lat), "p95Ms": round(p95, 1), "maxMs": round(max(lat) if lat else 0.0, 1)},
    }


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
                _record(status, ms)
                tenant = _tenant_of(request)
                sys.stdout.write(json.dumps({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "requestId": getattr(request.state, "request_id", ""),
                    "method": request.method, "path": request.url.path,
                    "status": status, "ms": round(ms, 1), "tenant": tenant,
                }) + "\n")
                sys.stdout.flush()
        return response
