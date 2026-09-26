"""Vantor API entrypoint — modular monolith, API-first.

Conventions enforced here:
- request-ID on every request/response (observability from day one)
- consistent error envelope (never a bare 500)
- OpenAPI generated from code at /api/docs (Phase 3 contract source)
"""
from __future__ import annotations

from fastapi import FastAPI

from .api import v1
from .core.errors import RequestIdMiddleware, install_error_handlers
from .core.idempotency import IdempotencyMiddleware
from .core.observe import AccessLogMiddleware
from .core.ratelimit import RateLimitMiddleware
from .core.secheaders import SecurityHeadersMiddleware

app = FastAPI(title="Vantor API", version="0.8.0-one-stop", openapi_url="/api/openapi.json", docs_url="/api/docs")
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
