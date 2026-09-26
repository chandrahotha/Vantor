"""Consistent error envelope + request-ID middleware.

Envelope (per docs/02-architecture/api.md):
  success: {"data": ..., "pagination": {...} | None, "error": None, "requestId": "..."}
  failure: {"data": None, "pagination": None, "error": {"code","message","details"}, "requestId": "..."}

Users never see a bare 500 without context.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
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
