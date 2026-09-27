"""Request observability — structured access log, per-route metrics, business counters.

Every request emits one JSON line (method, path, status, ms, tenant, requestId)
so any log collector can aggregate, and the same numbers are kept as
counter/histogram state that `GET /api/v1/ops/metrics` (admin-only) and
`/api/v1/ops/metrics.prom` expose.

VNT-033. This used to keep three global counters and one global latency
distribution. That is not a telemetry system:

* **No route dimension.** One endpoint taking 3s looked identical to every other
  endpoint taking 3ms. Finding the slow route was a matter of reading access logs
  by hand, which is exactly what a metrics backend exists to stop.
* **No p99.** A mean hides the tail, and the tail is what an SLO is written
  against. p95 of a global distribution across mixed routes is not the p95 of
  anything a user experienced.
* **No business signals.** "Requests are 200-ing" and "procurement is working"
  are different questions. A deployment where every webhook has been failing for
  a week and every approval times out reports a perfectly healthy request rate.
* **Cardinality was unbounded in principle.** Route labels are normalised
  through `core/paths.py`, the same function the rate limiter uses, and the
  per-route table is capped, so a caller generating random ids cannot create
  unbounded series.

The counters remain process-local, which is stated rather than hidden: for a
multi-replica deployment the collector aggregates them, and that is the honest
division of labour. Health probes are excluded to keep the signal clean, and no
PII is logged.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware

SKIP_PATHS = {"/api/v1/health", "/api/v1/ready", "/", "/api/docs", "/api/openapi.json", "/api/v1/ops/metrics", "/api/v1/ops/metrics.prom"}

#: Cap on distinct (method, route) series kept in memory. A misconfigured client
#: that hits a 404 with a random path segment on every request would otherwise
#: grow this table without bound. Beyond the cap the least-recently-seen series
#: are dropped, which costs a little history and keeps the process's footprint
#: predictable - the right trade when the alternative is an OOM in production.
MAX_ROUTE_SERIES = 2_000

#: Latency samples kept per series. Enough for a stable p99 over a scrape
#: interval, small enough that 2,000 series is a few megabytes rather than
#: hundreds.
_LATENCY_SAMPLES = 512

_lock = threading.Lock()
_counters = {"requests": 0, "errors5xx": 0, "errors4xx": 0}
_latencies: deque = deque(maxlen=4096)
_start = time.perf_counter()

#: (method, route) -> {"n", "err", latencies deque}
_routes: dict[tuple[str, str], dict] = {}

#: Named business counters: name -> {label tuple -> count}. Counters are declared
#: where the fact is known, so a signal cannot be forgotten in a dashboard file.
#:
#: Declared up front so the JSON snapshot lists them on a fresh install, where a
#: dashboard showing them at zero can be told apart from a dashboard that has
#: never heard of them. They are *not* emitted as zero-valued Prometheus series
#: before their first event: a bare unlabelled `..._total 0` alongside
#: labelled series would be double-counted by any `sum(rate(...))`, and a
#: missing series shows as "No data" in a way a labelled zero does not.
BUSINESS_COUNTERS: dict[str, dict[tuple[str, ...], int]] = {
    "vantor_webhook_deliveries": {},
    "vantor_esign_verifications": {},
    "vantor_approvals_decided": {},
    "vantor_money_posted": {},
    "vantor_ai_answers": {},
}


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = int(len(sorted_values) * fraction) - 1
    if index < 0:
        index = 0
    return sorted_values[index]


def record_request(method: str, route: str, status: int, ms: float) -> None:
    """Record one request: global counters *and* the per-route series.

    Single entry point on purpose. It used to be two calls - `_record` for the
    globals and `record_request` for the route - so a caller that reached for the
    obvious one recorded a route series and left the totals at zero, and the two
    metrics silently disagreed. One call, both updated.
    """
    key = (method.upper(), route)
    with _lock:
        _counters["requests"] += 1
        if status >= 500:
            _counters["errors5xx"] += 1
        elif status >= 400:
            _counters["errors4xx"] += 1
        _latencies.append(ms)

        if key not in _routes and len(_routes) >= MAX_ROUTE_SERIES:
            # Drop the oldest insertion first. `dict` preserves order, so this is
            # a cheap approximation of LRU rather than a full LRU.
            for stale in list(_routes)[: len(_routes) // 4 or 1]:
                _routes.pop(stale, None)
        series = _routes.get(key)
        if series is None:
            series = {"n": 0, "err": 0, "lat": deque(maxlen=_LATENCY_SAMPLES)}
            _routes[key] = series
        series["n"] += 1
        if status >= 500:
            series["err"] += 1
        series["lat"].append(ms)


def incr(name: str, *labels: str) -> None:
    """Bump a named business counter.

    Unknown names are accepted rather than rejected: a counter introduced by a
    newer worker should not crash an older web process that is still serving
    traffic during a rolling deploy.
    """
    with _lock:
        series = BUSINESS_COUNTERS.setdefault(name, {})
        key = tuple(labels)
        series[key] = series.get(key, 0) + 1


def metrics_snapshot() -> dict:
    with _lock:
        lat = sorted(_latencies)
        top = dict(_counters)
        routes = {
            f"{method} {route}": {
                "requests": s["n"],
                "errors5xx": s["err"],
                "p50Ms": round(_percentile(sorted(s["lat"]), 0.50), 1),
                "p95Ms": round(_percentile(sorted(s["lat"]), 0.95), 1),
                "p99Ms": round(_percentile(sorted(s["lat"]), 0.99), 1),
            }
            for (method, route), s in _routes.items()
        }
        business = {
            name: {"|".join(labels) or "_total": count for labels, count in series.items()}
            for name, series in BUSINESS_COUNTERS.items()
        }
    return {
        "process": {"uptimeSeconds": round(time.perf_counter() - _start, 1)},
        "requests": top,
        "latency": {
            "count": len(lat),
            "p50Ms": round(_percentile(lat, 0.50), 1),
            "p95Ms": round(_percentile(lat, 0.95), 1),
            "p99Ms": round(_percentile(lat, 0.99), 1),
            "maxMs": round(max(lat) if lat else 0.0, 1),
        },
        "routes": routes,
        "business": business,
    }


def prometheus_text() -> str:
    """Prometheus exposition for everything in `metrics_snapshot()`.

    Escaping matters: a route label goes into a quoted label value, and an
    unescaped quote or backslash there produces a document Prometheus refuses to
    parse - losing *every* metric rather than one.
    """
    def esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    snap = metrics_snapshot()
    lines: list[str] = []

    lines += [
        "# HELP vantor_http_requests_total Total requests by status class.",
        "# TYPE vantor_http_requests_total counter",
        f'vantor_http_requests_total{{class="5xx"}} {snap["requests"].get("errors5xx", 0)}',
        f'vantor_http_requests_total{{class="4xx"}} {snap["requests"].get("errors4xx", 0)}',
        f'vantor_http_requests_total{{class="all"}} {snap["requests"].get("requests", 0)}',
    ]

    lines += [
        "# HELP vantor_http_latency_ms Request latency in milliseconds.",
        "# TYPE vantor_http_latency_ms summary",
    ]
    for quantile, key in (("0.5", "p50Ms"), ("0.95", "p95Ms"), ("0.99", "p99Ms")):
        lines.append(
            f'vantor_http_latency_ms{{quantile="{quantile}"}} {snap["latency"][key]}'
        )

    lines += [
        "# HELP vantor_route_requests_total Requests by normalised route.",
        "# TYPE vantor_route_requests_total counter",
    ]
    for label, series in snap["routes"].items():
        method, _, route = label.partition(" ")
        lines.append(
            f'vantor_route_requests_total{{method="{esc(method)}",route="{esc(route)}"}} '
            f'{series["requests"]}'
        )
        lines.append(
            f'vantor_route_errors_total{{method="{esc(method)}",route="{esc(route)}"}} '
            f'{series["errors5xx"]}'
        )
        for quantile, key in (("0.5", "p50Ms"), ("0.95", "p95Ms"), ("0.99", "p99Ms")):
            lines.append(
                f'vantor_route_latency_ms{{method="{esc(method)}",route="{esc(route)}",'
                f'quantile="{quantile}"}} {series[key]}'
            )

    for name, series in snap["business"].items():
        metric = name if name.startswith("vantor_") else f"vantor_{name}"
        lines.append(f"# TYPE {metric} counter")
        for label, count in series.items():
            lines.append(f'{metric}{{event="{esc(label)}"}} {count}')

    return "\n".join(lines) + "\n"


def reset_metrics() -> None:
    """Clear all metric state. For tests, which need a known starting point."""
    global _start
    with _lock:
        _counters.update({"requests": 0, "errors5xx": 0, "errors4xx": 0})
        _latencies.clear()
        _routes.clear()
        for series in BUSINESS_COUNTERS.values():
            series.clear()
        _start = time.perf_counter()


def _is_test() -> bool:
    try:
        from .config import get_settings

        return get_settings().app_env == "test"
    except Exception:
        import os

        return os.getenv("APP_ENV") == "test"


async def _tenant_of_async(request) -> str:  # type: ignore[no-untyped-def]
    """Tenant for the access log, without blocking the event loop.

    `request.state.tenant_id` is set by `get_actor`, so the common case is free.
    The fallback exists for requests that reach the log without a resolved actor
    (a 401, a 404 before routing); there the token has to be verified, and that
    is CPU-bound, so it is handed to a worker thread rather than run inline in an
    `async def`.
    """
    from starlette.concurrency import run_in_threadpool

    state_tenant = getattr(request.state, "tenant_id", "") or ""
    if state_tenant:
        return state_tenant
    try:
        from .security import verify_token_async

        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return (await verify_token_async(auth[7:].strip())).tenant_id
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
                from .paths import route_label

                # Recorded by normalised route, so a dashboard can answer "which
                # endpoint is slow" instead of only "are requests succeeding".
                record_request(request.method, route_label(request.url.path), status, ms)
                request_id = getattr(request.state, "request_id", "")
                tenant = await _tenant_of_async(request)
                sys.stdout.write(json.dumps({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "requestId": request_id,
                    "method": request.method, "path": request.url.path,
                    "route": route_label(request.url.path),
                    "status": status, "ms": round(ms, 1), "tenant": tenant,
                }) + "\n")
                sys.stdout.flush()
        return response
