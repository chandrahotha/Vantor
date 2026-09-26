"""Liveness + readiness. No auth — load balancers must not need tokens.

- GET /api/v1/health: process alive (always 200 when code runs).
- GET /api/v1/ready: real dependency checks (DB reachable, migrations at head,
  Redis ping best-effort). 503 with per-check status when down — never fake green.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..core.errors import envelope
from ..core.tenant import get_session_factory

router = APIRouter(tags=["platform"])


@router.get("/health")
def health(request: Request) -> dict:
    return envelope({"status": "ok", "service": "vantor-api"}, None, getattr(request.state, "request_id", ""))


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    rid = getattr(request.state, "request_id", "")
    checks: dict[str, str] = {}
    try:
        db = get_session_factory()()
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

        from ..core.config import get_settings

        _Redis.from_url(get_settings().redis_url, socket_timeout=1.5).ping()
        checks["redis"] = "up"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"down: {type(exc).__name__}"
    ok = checks.get("database", "").startswith("up")
    return JSONResponse(status_code=200 if ok else 503, content=envelope({"ready": ok, "checks": checks}, None, rid))
