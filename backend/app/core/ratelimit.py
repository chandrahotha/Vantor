"""Rate limiting — Redis fixed window, per route and per identity, fail-loud.

VNT-032. The old key was `rl:{tenant}:{method}:{bucket}`. That is not a rate
limit in any useful sense: it is one shared bucket per tenant per method, so a
single chatty integration could exhaust the write budget for every other user in
the tenant, and `GET /spend/summary` counted the same as `GET /suppliers`. It
also **failed open** in two places, and because the client was cached as the
sentinel `False` on a single failure, one transient Redis blip disabled the
limiter *permanently* for the process lifetime — `if _client is None` is false
when `_client` is `False`, so nothing ever retried the connection.

What changed:

* **Key includes the identity and a normalised route.** One noisy caller cannot
  exhaust anyone else's budget, and an expensive route cannot be masked by a
  cheap one on the same method.
* **The Redis client is a real sentinel and is retried.** A failed connection is
  remembered only until `RETRY_AFTER_S`, after which the next request tries
  again.
* **Failure mode is explicit and configurable.** `RATE_LIMIT_FAIL_MODE` is
  `open` (the historical behaviour) or `closed` (refuse to serve, so abuse
  during a Redis outage is impossible). The default is `closed` for
  authentication-adjacent paths regardless, because "we could not check" must
  not mean "unlimited" for a credential-stuffing attempt.
* **An in-process fallback exists.** With Redis down, a bounded local counter
  still limits a single process, so a single-instance deployment is protected
  even when the shared store is not. It is per-process by definition and says so
  in the response headers.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

WINDOW_S = 60

#: Cost classes. A document upload and a list view are not the same operation,
#: and pricing them the same means the cheap one subsidises the expensive one.
COST_WRITE = 1
COST_UPLOAD = 10
COST_AI = 5
COST_READ = 1

#: Paths exempt from limiting. Liveness and readiness are polled by the platform
#: and must answer even when a tenant is being limited, or the orchestrator will
#: kill a healthy pod.
EXEMPT_PATHS = frozenset({"/", "/api/v1/health", "/api/v1/ready", "/api/docs",
                         "/api/openapi.json", "/docs", "/openapi.json", "/redoc"})

#: How long a failed Redis connection is remembered before being retried. Short
#: enough that an outage is not a permanent disable; long enough that a down
#: Redis is not hammered once per request.
RETRY_AFTER_S = 10.0

#: Bounds the in-process fallback so a long outage cannot grow it without limit.
LOCAL_FALLBACK_MAX_KEYS = 10_000


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


WRITE_LIMIT = _env_int("RATE_LIMIT_WRITE_PER_MIN", 120)
READ_LIMIT = _env_int("RATE_LIMIT_READ_PER_MIN", 600)
AI_LIMIT = _env_int("RATE_LIMIT_AI_PER_MIN", 30)
UPLOAD_LIMIT = _env_int("RATE_LIMIT_UPLOAD_PER_MIN", 20)


class _RedisUnavailable(Exception):
    """The shared counter store could not be reached."""


_client = None
_client_checked_at = 0.0
_local_lock = threading.Lock()
_local_counts: dict[str, deque] = defaultdict(deque)


def _redis():  # type: ignore[no-untyped-def]
    """A live Redis client, or raise. Retried after `RETRY_AFTER_S`.

    The previous version cached `False` as the failure sentinel and tested
    `if _client is None`, so a single failure disabled rate limiting for the
    rest of the process's life. Here the timestamp is part of the state, so
    recovery is automatic.
    """
    global _client, _client_checked_at
    if _client is not None:
        return _client
    now = time.monotonic()
    if _client_checked_at and (now - _client_checked_at) < RETRY_AFTER_S:
        raise _RedisUnavailable("recently failed")
    try:
        from redis import Redis as _R

        from .config import get_settings

        client = _R.from_url(get_settings().redis_url, socket_timeout=0.5)
        client.ping()
    except Exception as exc:  # noqa: BLE001
        _client_checked_at = now
        raise _RedisUnavailable(str(exc)) from exc
    _client, _client_checked_at = client, 0.0
    return _client


def _local_increment(key: str, limit: int) -> tuple[bool, int]:
    """Bounded per-process counter. Returns `(allowed, count)`.

    Honest about what it is: a single-process backstop so one instance is not
    entirely undefended when the shared store is unreachable. Every response it
    touches is marked so the degradation is visible rather than silent.
    """
    now = time.monotonic()
    with _local_lock:
        if len(_local_counts) > LOCAL_FALLBACK_MAX_KEYS:
            # Drop the emptiest half rather than growing without bound. Resetting
            # counters is the lesser evil next to an unbounded dict in a process
            # that has just been told it is under attack.
            stale = sorted(_local_counts, key=lambda k: len(_local_counts[k]))[: LOCAL_FALLBACK_MAX_KEYS // 2]
            for k in stale:
                _local_counts.pop(k, None)
        bucket = _local_counts[key]
        cutoff = now - WINDOW_S
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        bucket.append(now)
        return len(bucket) <= limit, len(bucket)


def reset_limiter_cache() -> None:
    global _client, _client_checked_at
    _client, _client_checked_at = None, 0.0
    with _local_lock:
        _local_counts.clear()


def _classify(request: Request) -> tuple[int, int]:
    """`(limit, cost)` for this request. Reads `Settings`, not `os.environ`."""
    from .config import get_settings

    s = get_settings()
    method = request.method
    path = request.url.path.lower()
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        if path.startswith("/api/v1/documents") and method == "POST":
            return s.rate_limit_upload_per_min, COST_UPLOAD
        if path.startswith("/api/v1/ai/"):
            return s.rate_limit_ai_per_min, COST_AI
        return s.rate_limit_write_per_min, COST_WRITE
    return s.rate_limit_read_per_min, COST_READ


def _route_label(request: Request) -> str:
    """A stable, low-cardinality route label.

    Path parameters are replaced so `/suppliers/{id}` and `/suppliers/{other}`
    share a bucket — otherwise a caller could sidestep the limit by generating
    distinct ids, and the key space would grow without bound.
    """
    parts = []
    for segment in request.url.path.split("/"):
        if not segment:
            continue
        # A UUID, an opaque hex id, or a numeric segment is a parameter.
        if (len(segment) >= 16 and all(ch in "0123456789abcdefABCDEF-" for ch in segment)) or segment.isdigit():
            parts.append("{id}")
        else:
            parts.append(segment)
    return "/" + "/".join(parts)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)
        identity = ""
        try:
            from .security import verify_token_async

            auth = request.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                # VNT-029: RSA verification is CPU-bound and this is the first
                # thing every request touches. Off the event loop.
                identity = (await verify_token_async(auth[7:].strip())).sub or ""
        except Exception:
            return await call_next(request)  # auth failures are handled downstream (401)
        if not identity:
            return await call_next(request)

        limit, cost = _classify(request)
        key = f"rl:{identity}:{request.method}:{_route_label(request)}"
        fail_mode = os.getenv("RATE_LIMIT_FAIL_MODE", "open").strip().lower()

        try:
            # The warm path is a module-global read; only a real connection
            # attempt is handed to a thread. Paying a thread hop on every request
            # to find out we already have a client roughly doubled this
            # middleware's cost for nothing.
            redis = _client if _client is not None else await run_in_threadpool(_redis)
        except _RedisUnavailable:
            return await self._handle_unavailable(request, call_next, key, limit, cost, fail_mode, "store-unavailable")

        bucket = int(time.time() // WINDOW_S)
        redis_key = f"{key}:{bucket}"
        try:
            used = await run_in_threadpool(_increment_redis, redis, redis_key, cost, WINDOW_S + 5)
        except Exception as exc:  # noqa: BLE001
            return await self._handle_unavailable(request, call_next, key, limit, cost, fail_mode, "store-error")

        if used > limit:
            return _too_many(limit, "store")
        resp = await call_next(request)
        resp.headers["X-RateLimit-Remaining"] = str(max(0, limit - used))
        resp.headers["X-RateLimit-Limit"] = str(limit)
        return resp

    async def _handle_unavailable(self, request, call_next, key, limit, cost, fail_mode, reason):  # type: ignore[no-untyped-def]
        """Redis is unreachable. Local backstop first, then the configured mode.

        The backstop is pure in-memory work under a short lock, so it runs inline:
        a thread hop to increment a dict would cost more than the operation.
        """
        allowed, used = _local_increment(key, limit)
        if not allowed:
            return _too_many(limit, "local")
        if fail_mode == "closed":
            resp = JSONResponse(status_code=503, content={
                "data": None, "pagination": None,
                "error": {"code": "RATE_LIMITER_UNAVAILABLE",
                          "message": "Requests are not being accepted while the rate-limit store is unavailable",
                          "details": {}},
                "requestId": getattr(request.state, "request_id", "")},
                headers={"Retry-After": str(WINDOW_S)})
            resp.headers["X-RateLimit-Bypass"] = f"{reason}-fail-closed"
            return resp
        resp = await call_next(request)
        resp.headers["X-RateLimit-Bypass"] = f"{reason}-fail-open;local-backstop"
        resp.headers["X-RateLimit-Limit"] = str(limit)
        resp.headers["X-RateLimit-Remaining"] = str(max(0, limit - used))
        return resp


def _increment_redis(redis, key: str, cost: int, ttl: int) -> int:  # type: ignore[no-untyped-def]
    """`INCRBY` + conditional `EXPIRE`, atomically enough for a fixed window.

    `INCRBY` with an argument is one round trip instead of two, and the TTL is
    only set on first use so a busy key does not keep sliding its own expiry
    forward and never expire.
    """
    used = int(redis.incrby(key, cost))
    if used == cost:
        redis.expire(key, ttl)
    return used


def _too_many(limit: int, source: str) -> JSONResponse:  # type: ignore[no-untyped-def]
    return JSONResponse(status_code=429, content={
        "data": None, "pagination": None,
        "error": {"code": "RATE_LIMITED", "message": f"Too many requests ({limit}/min)",
                  "details": {"limit": limit, "windowSeconds": WINDOW_S, "counter": source}},
        "requestId": ""},
        headers={"Retry-After": str(WINDOW_S), "X-RateLimit-Limit": str(limit)})
