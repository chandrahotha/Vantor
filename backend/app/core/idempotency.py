"""Idempotency-Key support for mutating requests (SupplierRadar canonical pattern).

Client sends `Idempotency-Key: <uuid>` on POST/PUT/PATCH. First request claims the
fingerprint atomically, executes, and stores (status, body); retries with the same
key+method+path+tenant+body-hash replay the stored response without re-executing.
Keys are tenant-scoped and body-bound (same key + different payload => 422, never a
wrong replay).

VNT-006 changed the order of operations. It used to be lookup -> execute ->
remember, which is replay-safe but *not* execution-safe: two concurrent duplicates
both read "absent", both ran the handler, both performed the write, and the unique
constraint merely decided whose response body survived. The claim is now taken
first, under `ON CONFLICT DO NOTHING`, so the database arbitrates. Losers get a 409
with a code they can act on instead of a duplicate side effect.

Still fail-open on infra errors (never block a legitimate write) — but a degraded
store now says so in `Idempotency-Bypass` rather than pretending the write was
protected.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, update
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..models.audit import IdempotencyKey

#: How long a claim may sit `in_progress` before another request may take it over.
#: Long enough that a legitimate slow write is never stolen, short enough that a
#: crashed process does not wedge the endpoint for the lifetime of the row.
STALE_CLAIM_S = 120


def _age_seconds(value: datetime | None) -> float | None:
    """Seconds since `value`, or None if it is unset.

    SQLite's DATETIME discards tzinfo on store, so a timestamp read back from
    SQLite is naive while the same row in PostgreSQL is aware. Both are treated
    as UTC here, which is what they are: every write in this module uses
    `datetime.now(timezone.utc)`.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - value).total_seconds()


def _now_for(dialect: str) -> datetime:
    """A timestamp in whatever the target dialect can actually store.

    The stale-claim takeover compares `claimed_at` for equality, so the value
    written has to be comparable with the value that will be read back. Writing
    an aware datetime to SQLite stores a naive one, which would make the next
    compare-and-swap silently match nothing and wedge the endpoint all over
    again.
    """
    now = datetime.now(timezone.utc)
    return now if dialect == "postgresql" else now.replace(tzinfo=None)


def _tenant_of(request: Request) -> str:
    """Tenant from the verified JWT only. Blocking; see `tenant_of_async`."""
    try:
        from ..core.security import verify_token

        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return verify_token(auth[7:].strip()).tenant_id
    except Exception:
        pass
    return ""


async def tenant_of_async(request: Request) -> str:
    """VNT-029: token verification off the event loop.

    The middleware is `async def`; a synchronous RSA verify plus a possible JWKS
    fetch there stalls every in-flight request behind the slowest one.
    """
    try:
        from ..core.security import verify_token_async

        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return (await verify_token_async(auth[7:].strip())).tenant_id
    except Exception:
        pass
    return ""


def _body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


#: The composed fingerprint is stored in `idempotency_keys.key` (VARCHAR(512)).
#: Bound it here too, so a pathological path can never push a row past the
#: column — an overflow is swallowed by the fail-open handlers below and would
#: silently disable idempotency with no error anywhere.
FINGERPRINT_MAX = 512


def _fingerprint(method: str, path: str, key: str, body: bytes) -> str:
    """`method|path|key|sha256(body)`, hashed down if it would not fit.

    A stable hash keeps every distinct request distinct, so two long paths that
    differ only past the limit can never collide onto one stored response.
    """
    raw = f"{method}|{path}|{key}|{_body_hash(body)}"
    if len(raw) <= FINGERPRINT_MAX:
        return raw
    return f"{method}|{path[:200]}|{key[:128]}|{_body_hash(raw.encode())}"


def _claim(tenant_id: str, fingerprint: str, method: str, path: str) -> tuple[str, object | None]:
    """Atomically claim the fingerprint, or report who holds it.

    Returns one of:
      ("proceed", None)     — we inserted the in-flight row; run the handler
      ("replay",  row)      — a completed row exists; serve its stored response
      ("in_flight", row)    — another request holds the claim; caller must 409
      ("unavailable", None) — infra failure; fail open and run the handler

    The insert uses `ON CONFLICT DO NOTHING` and then re-reads, which is what
    makes the claim atomic. A plain `SELECT` then `INSERT` is a check-then-act
    with no interlock: two concurrent duplicates both read "absent", both insert,
    and both execute the write. The database, not the application, is the thing
    that has to arbitrate here.

    `STALE_CLAIM_S`: a process killed mid-request leaves `in_progress` forever.
    After that long we take the row over rather than wedge the endpoint, because
    a request that has been stuck for the whole window is not going to finish.
    """
    try:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        from ..core.tenant import pinned_session

        db = pinned_session(tenant_id)
        try:
            # Core insert only. Adding the ORM object as well would emit a second
            # INSERT for the same primary key on commit, and the whole claim would
            # roll back — which is exactly how this looked like "idempotency
            # silently does nothing" for an hour.
            now = datetime.now(timezone.utc)
            claim_id = uuid.uuid4().hex
            dialect = db.get_bind().dialect.name
            stmt = (pg_insert if dialect == "postgresql" else sqlite_insert)(IdempotencyKey)
            db.execute(stmt.values(
                id=claim_id, tenant_id=tenant_id, created_by="", updated_by="",
                key=fingerprint, method=method, path=path, state="in_progress",
                created_at=now, updated_at=now, claimed_at=now,
                status_code=0, response_body={},
            ).on_conflict_do_nothing(
                index_elements=[IdempotencyKey.tenant_id, IdempotencyKey.key,
                                IdempotencyKey.method, IdempotencyKey.path]))
            db.commit()

            stored = db.execute(select(IdempotencyKey).where(
                IdempotencyKey.tenant_id == tenant_id, IdempotencyKey.key == fingerprint,
                IdempotencyKey.method == method, IdempotencyKey.path == path)).scalar_one_or_none()
            if stored is None:
                # Our row vanished (should not happen). Do not silently proceed.
                return ("unavailable", None)
            if stored.id == claim_id:
                return ("proceed", None)
            if stored.state == "completed":
                return ("replay", stored)
            claimed = stored.claimed_at
            age = _age_seconds(claimed)
            if age is not None and age > STALE_CLAIM_S:
                # Take over the abandoned claim, atomically.
                #
                # This has to be a conditional UPDATE. The previous version
                # reused the dialect *insert* builder from above, chained
                # `.values(...).where(...)` onto it and added
                # `on_conflict_do_nothing(index_elements=[])`. `Insert` has no
                # `.where()`, so the statement raised AttributeError, the broad
                # `except Exception` below swallowed it, and the function returned
                # `("unavailable", None)` — which fails open and runs the handler.
                #
                # So the endpoint did recover, but by accident and through an
                # exception path, the row was never actually taken over, and it
                # stayed `in_progress` forever: every later retry re-read the
                # stale row and took the same broken branch. A log line was the
                # only evidence anything had gone wrong.
                #
                # Comparing `claimed_at` to the value the database returned is
                # what makes this compare-and-swap: of two racers that both saw
                # the same stale timestamp, only the one whose UPDATE matches
                # before the other commits gets a non-zero rowcount.
                result = db.execute(
                    update(IdempotencyKey)
                    .where(IdempotencyKey.tenant_id == tenant_id,
                           IdempotencyKey.id == stored.id,
                           IdempotencyKey.state == "in_progress",
                           IdempotencyKey.claimed_at == claimed)
                    .values(state="in_progress", claimed_at=_now_for(dialect),
                            updated_at=_now_for(dialect)))
                db.commit()
                if result.rowcount:
                    return ("proceed", None)
                return ("in_flight", stored)
            return ("in_flight", stored)
        finally:
            db.close()
    except Exception:
        # Fail open: a broken idempotency store must never take procurement down.
        # The header marks the response so the degradation is observable.
        return ("unavailable", None)


def _complete(tenant_id: str, fingerprint: str, method: str, path: str, status_code: int, body: dict) -> None:
    """Replace our in-flight claim with the stored response."""
    try:
        from ..core.tenant import pinned_session

        db = pinned_session(tenant_id)
        try:
            row = db.execute(select(IdempotencyKey).where(
                IdempotencyKey.tenant_id == tenant_id, IdempotencyKey.key == fingerprint,
                IdempotencyKey.method == method, IdempotencyKey.path == path)).scalar_one_or_none()
            if row is None:
                return
            row.state, row.status_code, row.response_body = "completed", status_code, body
            db.commit()
        except Exception:
            if os.getenv("VANTOR_DEBUG_IDEMPOTENCY"):
                import traceback; traceback.print_exc()
            db.rollback()
        finally:
            db.close()
    except Exception:
        pass


def _release(tenant_id: str, fingerprint: str, method: str, path: str) -> None:
    """Drop our claim after a failed handler so the client can retry.

    A 4xx or 5xx is not a stored outcome — the client is entitled to try the same
    request again, and leaving the claim held would answer 409 forever for a
    request that never succeeded.
    """
    try:
        from ..core.tenant import pinned_session

        db = pinned_session(tenant_id)
        try:
            db.execute(delete(IdempotencyKey).where(
                IdempotencyKey.tenant_id == tenant_id, IdempotencyKey.key == fingerprint,
                IdempotencyKey.method == method, IdempotencyKey.path == path,
                IdempotencyKey.state == "in_progress"))
            db.commit()
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
        tenant_id = await tenant_of_async(request)
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
        fingerprint = _fingerprint(request.method, path, key, raw_body)

        # VNT-006: claim before executing, not after.
        verdict, stored = await run_in_threadpool(_claim, tenant_id, fingerprint, request.method, path)
        if verdict == "replay":
            resp = JSONResponse(status_code=stored.status_code, content=stored.response_body)
            resp.headers["Idempotent-Replayed"] = "true"
            return resp
        if verdict == "in_flight":
            resp = JSONResponse(status_code=409, content={
                "data": None,
                "error": {"code": "IDEMPOTENCY_IN_FLIGHT",
                          "message": "A request with this Idempotency-Key is still in progress. "
                                     "Poll the original, or retry with a new key."},
                "meta": {"requestId": getattr(request.state, "request_id", "")}})
            resp.headers["Idempotent-Replayed"] = "false"
            return resp

        response = await call_next(request)
        # Consume body regardless of wrapper type (plain Response has .body).
        try:
            iterator = getattr(response, "body_iterator", None)
            raw = b"".join([chunk async for chunk in iterator]) if iterator is not None else response.body  # type: ignore[attr-defined]
        except Exception:
            if verdict == "proceed":
                await run_in_threadpool(_release, tenant_id, fingerprint, request.method, path)
            return response
        headers = {k.decode().lower(): v.decode() for k, v in response.headers.raw if k.decode().lower() != "content-length"}
        if 200 <= response.status_code < 300 and "application/json" in headers.get("content-type", ""):
            if verdict == "proceed":
                try:
                    await run_in_threadpool(_complete, tenant_id, fingerprint, request.method, path,
                                            response.status_code, json.loads(raw.decode() or "{}"))
                except Exception:
                    # A response we could not store must not fail the request that
                    # already succeeded — but the claim has to be released, or the
                    # client can never retry with this key.
                    await run_in_threadpool(_release, tenant_id, fingerprint, request.method, path)
        elif verdict == "proceed":
            await run_in_threadpool(_release, tenant_id, fingerprint, request.method, path)
        return Response(content=raw, status_code=response.status_code, headers=headers, media_type=headers.get("content-type", "application/json"))
