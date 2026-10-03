"""Tenant context + DB session with RLS enforcement.

Every request runs with `SET LOCAL app.tenant_id = '<tenant>'` inside a
transaction so Postgres RLS policies (`tenant_id = current_setting(...)`)
hold even if application filters are forgotten. Defense in depth:
application-level `tenant_id` filters remain mandatory; RLS is the backstop.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_settings

_engine = None
_SessionLocal: sessionmaker | None = None

#: Key under `Session.info` holding the tenant a session is pinned to. See
#: `_reapply_tenant_pin_on_every_transaction`.
_TENANT_INFO_KEY = "vantor_tenant_id"


@event.listens_for(Session, "after_begin")
def _reapply_tenant_pin_on_every_transaction(session, transaction, connection):  # type: ignore[no-untyped-def]
    """Re-apply the tenant pin at the start of every transaction, not just the
    first.

    `set_config(..., true)` ("SET LOCAL") correctly resets when a transaction
    commits or rolls back — that is what keeps a connection returning to the
    pool from carrying one request's tenant context into the next request that
    happens to reuse it. But several routers call `db.commit()` mid-handler
    and keep using the same session afterward (`db.refresh(row)` immediately
    after `db.commit()` is a repeated pattern across routers). Once RLS
    actually applies to the application's own role (migration
    0026_app_role_least_privilege), that second, post-commit transaction has
    no tenant context, and the row the handler just wrote becomes invisible to
    its own RLS policy — not a tenant leak, but a fail-closed `500` on most
    write endpoints. Reproduced live: `POST /suppliers` 500'd on
    `db.refresh(row)` with `InvalidRequestError: Could not refresh instance`
    the first time this was exercised with RLS actually enforced; previously
    invisible because every connection had RLS silently bypassed outright.

    A first attempt stashed the tenant on `Connection.info` instead of here —
    wrong, because `Session.commit()` does not guarantee the *same* physical
    connection backs the session's next transaction (it can return to the
    pool and a different one can be checked out). `Session.info` belongs to
    the Session object itself, independent of which connection backs any
    given transaction, which is what makes this correct across a mid-handler
    commit regardless of pooling. This listener is global (bound to the
    `Session` class, registered once at import time) and a no-op for any
    session that never had its tenant pinned (`session.info` empty).
    """
    tenant_id = session.info.get(_TENANT_INFO_KEY)
    if tenant_id and connection.dialect.name == "postgresql":
        connection.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})


def get_engine():  # type: ignore[no-untyped-def]
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url_resolved
        if url.startswith("sqlite"):
            # Unit-test / local only: shared in-memory DB across threads
            # (StaticPool + shared cache) so TestClient sees created tables.
            _engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            _engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), class_=Session, expire_on_commit=False)
    return _SessionLocal


def get_db(tenant_id: str = "") -> Generator[Session, None, None]:
    """Yield a transactional session pinned to tenant_id for RLS.

    Use as FastAPI dep via `db_for_actor` below so tenant always comes from
    the verified JWT, never from a query param.
    """
    factory = get_session_factory()
    db = factory()
    try:
        if tenant_id and db.bind.dialect.name == "postgresql":
            # `session.info` makes `_reapply_tenant_pin_on_every_transaction` pin
            # every transaction this session opens — including one after a
            # mid-handler `db.commit()` — without every call site doing it by hand.
            db.info[_TENANT_INFO_KEY] = tenant_id
            db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def pinned_session(tenant_id: str) -> Session:
    """Standalone session pinned to `tenant_id` — for callers outside the
    request/dependency cycle (middleware, SSE generators, background work).

    Raw `get_session_factory()()` is NOT safe: on Postgres the RLS `WITH CHECK`
    on tenant-scoped tables rejects the write, and a broad `except` then hides
    it. Always pin. Callers own commit/rollback/close.
    """
    db = get_session_factory()()
    if tenant_id and db.bind.dialect.name == "postgresql":
        db.info[_TENANT_INFO_KEY] = tenant_id
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
    return db


def reset_engine_cache() -> None:
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None
