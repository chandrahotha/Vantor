"""Consistent error envelope + request-ID middleware.

Envelope (per docs/02-architecture/api.md):
  success: {"data": ..., "pagination": {...} | None, "error": None, "requestId": "..."}
  failure: {"data": None, "pagination": None, "error": {"code","message","details"}, "requestId": "..."}

Users never see a bare 500 without context.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

#: An inbound `X-Request-ID` was accepted verbatim, with no length bound and no
#: character class, and was then reflected into the response header *and* every
#: JSON envelope body. A caller could therefore inject newlines, control
#: characters, or megabytes of text into every response and into the access log.
#:
#: The character class is the actual control: it admits the shapes correlation
#: ids really use (hex, UUID, dotted and colon-separated trace ids) and excludes
#: everything a header-splitting or log-forging attack needs. There is no
#: minimum length — a short id is harmless, and inventing one would reject
#: legitimate callers for no security benefit.
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,63}$")
REQUEST_ID_MAX = 64


def sanitize_request_id(candidate: str | None) -> str:
    """Return `candidate` if it is a safe, bounded correlation id, else a fresh one."""
    if candidate:
        value = candidate.strip()
        if len(value) <= REQUEST_ID_MAX and REQUEST_ID_PATTERN.match(value):
            return value
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = sanitize_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def envelope(data: Any = None, pagination: dict | None = None, request_id: str = "") -> dict:
    return {"data": data, "pagination": pagination, "error": None, "requestId": request_id}


def error_envelope(code: str, message: str, details: Any = None, request_id: str = "") -> dict:
    return {
        "data": None,
        "pagination": None,
        "error": {"code": code, "message": message, "details": details or {}},
        "requestId": request_id,
    }


def install_error_handlers(app: FastAPI) -> None:
    def _harden(resp: JSONResponse, rid: str) -> JSONResponse:
        # Error paths bypass SecurityHeadersMiddleware — harden here instead.
        from .secheaders import apply_security_headers

        try:
            from .config import get_settings

            prod = get_settings().is_prod
        except Exception:
            prod = False
        apply_security_headers(resp, is_prod=prod)
        resp.headers["X-Request-ID"] = rid
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = getattr(request.state, "request_id", "")
        # ctx may hold non-serializable objects — coerce safely.
        details = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
        return _harden(JSONResponse(
            status_code=422,
            content=error_envelope("VALIDATION_FAILED", "Request validation failed", details, rid),
        ), rid)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        rid = getattr(request.state, "request_id", "")
        detail = exc.detail
        extra: dict[str, Any]
        if isinstance(detail, dict) and "code" in detail:
            code = str(detail.get("code", "REQUEST_FAILED"))
            message = str(detail.get("message", "Request failed"))
            extra = detail.get("details", {})
        else:
            code = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND",
                    409: "CONFLICT", 413: "PAYLOAD_TOO_LARGE", 422: "UNPROCESSABLE", 502: "BAD_GATEWAY",
                    503: "UNAVAILABLE"}.get(exc.status_code, "REQUEST_FAILED")
            message = detail if isinstance(detail, str) else "Request failed"
            extra = {} if isinstance(detail, str) else jsonable_encoder(detail, custom_encoder={Exception: str})
        return _harden(JSONResponse(status_code=exc.status_code, content=error_envelope(code, message, extra, rid)), rid)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # noqa: BLE001
        rid = getattr(request.state, "request_id", "")
        # Never leak internals; log full traceback via structlog/uvicorn upstream.
        return _harden(JSONResponse(
            status_code=500,
            content=error_envelope("INTERNAL_ERROR", "Unexpected error processing request", {}, rid),
        ), rid)
