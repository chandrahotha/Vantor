"""Idempotency-Key support for mutating requests (SupplierRadar canonical pattern).

Client sends `Idempotency-Key: <uuid>` on POST/PUT/PATCH. First request executes
and stores (status, body); retries with the same key+method+path+tenant+body-hash
replay the stored response without re-executing. Keys are tenant-scoped and
body-bound (same key + different payload => 422, never a wrong replay).
Best-effort and fail-open on infra errors (never block a legitimate write).
"""
from __future__ import annotations

import hashlib
import json

from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..models.audit import IdempotencyKey


def _tenant_of(request: Request) -> str:
    # Tenant comes from the verified JWT only (never a header/param).
    try:
        from ..core.security import verify_token

        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return verify_token(auth[7:].strip()).tenant_id
    except Exception:
        pass
    return ""


def _body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _lookup(tenant_id: str, fingerprint: str):  # type: ignore[no-untyped-def]
    try:
        from ..core.tenant import pinned_session

        db = pinned_session(tenant_id)
        try:
            return db.execute(select(IdempotencyKey).where(
                IdempotencyKey.tenant_id == tenant_id, IdempotencyKey.key == fingerprint)
            ).scalar_one_or_none()
        finally:
            db.close()
    except Exception:
        return None


def _remember(tenant_id: str, fingerprint: str, method: str, path: str, status_code: int, body: dict) -> None:
    try:
        from ..core.tenant import pinned_session

        # Pinned, not raw: RLS `WITH CHECK` on idempotency_keys would otherwise
        # reject this insert on Postgres and the broad `except` would hide it,
        # silently disabling idempotency in production while tests pass on SQLite.
        db = pinned_session(tenant_id)
        try:
            db.add(IdempotencyKey(tenant_id=tenant_id, created_by="", updated_by="",
                                  key=fingerprint, method=method, path=path,
                                  status_code=status_code, response_body=body))
            db.commit()
        except IntegrityError:
            db.rollback()  # concurrent same-key winner already stored — keep theirs
        except Exception:
            db.rollback()
        finally:
            db.close()
    except Exception:
        pass


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method not in {"POST", "PUT", "PATCH"}:
            return await call_next(request)
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key or len(key) > 128:
            return await call_next(request)
        tenant_id = _tenant_of(request)
        if not tenant_id:
            return await call_next(request)
        path = request.url.path
        # Read + restore the body so downstream still sees it (BaseHTTPMiddleware consumes the stream).
        try:
            raw_body = await request.body()
        except Exception:
            return await call_next(request)

        async def _receive():  # type: ignore[no-untyped-def]
            return {"type": "http.request", "body": raw_body, "more_body": False}

        request = Request(request.scope, _receive)
        fingerprint = f"{request.method}|{path}|{key}|{_body_hash(raw_body)}"
        stored = _lookup(tenant_id, fingerprint)
        if stored is not None:
            resp = JSONResponse(status_code=stored.status_code, content=stored.response_body)
            resp.headers["Idempotent-Replayed"] = "true"
            return resp

        response = await call_next(request)
        # Consume body regardless of wrapper type (plain Response has .body).
        try:
            iterator = getattr(response, "body_iterator", None)
            raw = b"".join([chunk async for chunk in iterator]) if iterator is not None else response.body  # type: ignore[attr-defined]
        except Exception:
            return response
        headers = {k.decode().lower(): v.decode() for k, v in response.headers.raw if k.decode().lower() != "content-length"}
        if 200 <= response.status_code < 300 and "application/json" in headers.get("content-type", ""):
            try:
                _remember(tenant_id, fingerprint, request.method, path, response.status_code, json.loads(raw.decode() or "{}"))
            except Exception:
                pass
        return Response(content=raw, status_code=response.status_code, headers=headers, media_type=headers.get("content-type", "application/json"))
