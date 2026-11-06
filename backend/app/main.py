"""Vantor API entrypoint — modular monolith, API-first.

Conventions enforced here:
- request-ID on every request/response (observability from day one)
- consistent error envelope (never a bare 500)
- OpenAPI generated from code at /api/docs (Phase 3 contract source)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import v1
from .core.errors import RequestIdMiddleware, install_error_handlers
from .core.idempotency import IdempotencyMiddleware
from .core.observe import AccessLogMiddleware
from .core.ratelimit import RateLimitMiddleware
from .core.secheaders import SecurityHeadersMiddleware

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create the schema when the store is SQLite.

    Alembic owns the PostgreSQL schema — it carries the RLS policies, the
    composite foreign keys and the pgvector index, none of which SQLite has —
    so this deliberately does nothing there and would be wrong if it did.

    SQLite had no owner at all. It was only ever used by the test fixtures,
    which call `create_all` themselves, so a real single-container deployment
    pointed at a SQLite file started successfully and then answered 500 on
    every route because no table existed. `create_all` is additive and skips
    tables that are already present, so this is safe on every boot after the
    first.
    """
    from .core.config import get_settings
    settings = get_settings()
    if settings.database_url_resolved.startswith("sqlite"):
        from .core.tenant import get_engine
        from .models.registry import Base
        Base.metadata.create_all(get_engine())
    else:
        # Postgres. Ask the database whether the row-level-security backstop can
        # actually apply to this connection before serving a single request:
        # superusers, BYPASSRLS roles and table owners all ignore it, so a
        # deployment that connects as the migration role has no DB-side tenant
        # isolation at all while every endpoint still returns the right rows for
        # the tenant its filters chose. Migration 0026 documents twenty-nine
        # migrations spent in exactly that state. Production refuses; elsewhere
        # it warns, and `/ready` reports the answer either way.
        import warnings

        from .core.tenant import rls_backstop, rls_verdict

        status = rls_backstop()
        ok, message = rls_verdict(status, settings.is_prod)
        if not ok:
            raise RuntimeError(message)
        if status.get("applicable") and not status.get("enforced"):
            warnings.warn(message, RuntimeWarning, stacklevel=2)
    yield


app = FastAPI(title="Vantor API", version="0.8.0-one-stop", openapi_url="/api/openapi.json", docs_url="/api/docs", lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)
install_error_handlers(app)
app.include_router(v1)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": "vantor-api", "docs": "/api/docs", "health": "/api/v1/health"}
