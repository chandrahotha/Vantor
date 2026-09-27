"""Tenant context + DB session with RLS enforcement.

Every request runs with `SET LOCAL app.tenant_id = '<tenant>'` inside a
transaction so Postgres RLS policies (`tenant_id = current_setting(...)`)
hold even if application filters are forgotten. Defense in depth:
application-level `tenant_id` filters remain mandatory; RLS is the backstop.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_settings

_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():  # type: ignore[no-untyped-def]
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url_resolved
        if url.startswith("sqlite"):
            # Unit-test / local only: shared in-memory DB across threads
            # (StaticPool + shared cache) so TestClient sees created tables.
            _engine = create_engine(
                "sqlite:///:memory:?cache=shared",
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
            # Session is already inside a transaction; SET LOCAL scopes RLS to it.
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
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
    return db


def reset_engine_cache() -> None:
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None
