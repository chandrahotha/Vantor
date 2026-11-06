"""Liveness + readiness. No auth — load balancers must not need tokens.

- GET /api/v1/health: process alive (always 200 when code runs).
- GET /api/v1/ready: real dependency checks (DB reachable, migrations at head,
  Redis ping best-effort). 503 with per-check status when down — never fake green.
- GET /api/v1/ops/metrics: in-process request/latency counters. Admin roles only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..core.errors import envelope
from ..core.config import get_settings
from ..core.observe import metrics_snapshot, prometheus_text
from ..core.security import Actor, get_actor
from ..core.tenant import probe_session

router = APIRouter(tags=["platform"])


@router.get("/health")
def health(request: Request) -> dict:
    return envelope({"status": "ok", "service": "vantor-api"}, None, getattr(request.state, "request_id", ""))


@router.get("/ops/metrics")
def ops_metrics(request: Request, actor: Actor = Depends(get_actor)) -> dict:
    """Perf counters for this process. Auditor/Super Admin only — a request-count
    by tenant is a real information-leak surface, so it is role-gated, not public.
    Sums are per-process; a multi-replica deploy needs a collector (Phase 10)."""
    if not set(actor.roles or ()) & {"Super Admin", "Auditor", "Organization Admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return envelope(metrics_snapshot(), None, getattr(request.state, "request_id", ""))


@router.get("/ops/metrics.prom")
def ops_metrics_prometheus(actor: Actor = Depends(get_actor)) -> Response:
    """Prometheus exposition for this process. Same role gate as the JSON variant
    — scrapes still need a service principal, because a request count by tenant is
    a real information-leak surface.

    VNT-033. The body used to be assembled by hand here, and it was invalid: every
    line was emitted as `vantor_http_requests_total {class="5xx"} 0`, and the
    exposition format does not allow whitespace between the metric name and the
    label set. Prometheus rejects the *whole document* on that, so the endpoint
    returned 200 with a body no scraper would accept — a scrape that looked
    healthy and recorded nothing. The renderer now lives beside the counters it
    renders, and escapes label values, because an unescaped quote in a label also
    costs every metric rather than one.
    """
    if not set(actor.roles or ()) & {"Super Admin", "Auditor", "Organization Admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return Response(prometheus_text(), media_type="text/plain; version=0.0.4")


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    rid = getattr(request.state, "request_id", "")
    checks: dict[str, str] = {}
    try:
        # `probe_session()` rather than a pinned one: this reads `SELECT 1` and
        # `alembic_version`, neither of which is a tenant table, and there is no
        # actor at this endpoint to derive a tenant from.
        db = probe_session()
        try:
            db.execute(text("SELECT 1"))
            try:
                head = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
                checks["database"] = f"up (migrations@{head})" if head else "down: unmigrated (no alembic_version)"
            except Exception:
                checks["database"] = "down: unmigrated"
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 — surface as check, not traceback
        checks["database"] = f"down: {type(exc).__name__}"
    try:
        from redis import Redis as _Redis

        _Redis.from_url(get_settings().redis_url, socket_timeout=1.5).ping()
        checks["redis"] = "up"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"down: {type(exc).__name__}"
    ok = checks.get("database", "").startswith("up")
    # Reported, never gating: passwordless local auth is a supported identity
    # mode, not an outage, and failing readiness on it would break the
    # single-container deployment that depends on this endpoint passing. What it
    # does is make the mode visible after boot instead of only in a config file —
    # an operator or a scanner can ask the running process who can sign in.
    identity = get_settings()
    checks["identity"] = (
        f"local (AUTH_MODE={identity.auth_mode}) — passwordless: any caller who can "
        "reach this API is the local operator"
        if identity.passwordless_local_auth
        else f"oidc (AUTH_MODE={identity.auth_mode}) — tokens must be signed by {identity.oidc_issuer}"
    )
    # The RLS answer, re-read here rather than cached from startup: the question
    # "is the backstop engaged" is about the connection this process holds, and a
    # readiness probe is the thing an operator already polls when they suspect the
    # deployment is not what they meant to deploy.
    from ..core.tenant import rls_backstop

    rls = rls_backstop()
    checks["rls"] = ("enforced as " + str(rls.get("role", "?"))) if rls.get("enforced") \
        else f"not enforced: {rls.get('reason')}"
    return JSONResponse(status_code=200 if ok else 503, content=envelope({"ready": ok, "checks": checks}, None, rid))
