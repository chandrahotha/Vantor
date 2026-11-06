"""Tenant context + DB session with RLS enforcement.

Every request runs with `SET LOCAL app.tenant_id = '<tenant>'` inside a
transaction so Postgres RLS policies (`tenant_id = current_setting(...)`)
hold even if application filters are forgotten. Defense in depth:
application-level `tenant_id` filters remain mandatory; RLS is the backstop.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, make_url, text
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
            # Two different SQLite deployments were being given the same pool,
            # and only one of them needed it.
            #
            # **In-memory** SQLite (`sqlite://`, `sqlite:///:memory:`) is one
            # database that exists only for the lifetime of its connection, so
            # every session must share that one connection — `StaticPool` is
            # the only pool that can do that, and `check_same_thread=False`
            # lets the test client and the request threads share it.
            #
            # **File-backed** SQLite (`sqlite:///./vantor.db`) is an ordinary
            # database on disk. Forcing it through the same pool gave the
            # single-container deployment *one connection shared by every
            # request thread*, and a SQLite connection is not safe for
            # concurrent use: two requests interleaving on it produced
            # `sqlite3.InterfaceError: bad parameter or other API misuse` and
            # `IndexError: tuple index out of range` inside SQLAlchemy's
            # result processing. Those surfaced as 500s the browser could not
            # read, because a response produced by an unhandled exception never
            # passes back through the CORS middleware — so the page saw an
            # opaque network error instead of an error it could act on.
            #
            # The file-backed case therefore uses the dialect's own default
            # (`QueuePool`, `check_same_thread=False`), which hands each thread
            # its own connection. This is the same pool SQLAlchemy chooses on
            # its own for a file database.
            database = make_url(url).database
            in_memory = database in (None, "", ":memory:")
            if in_memory:
                _engine = create_engine(
                    url,
                    connect_args={"check_same_thread": False},
                    poolclass=StaticPool,
                )
            else:
                _engine = create_engine(
                    url,
                    connect_args={"check_same_thread": False},
                    pool_pre_ping=True,
                )
        else:
            _engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)
    return _engine


def _session_factory() -> sessionmaker:
    """The raw sessionmaker. Private on purpose — see `probe_session`.

    A session from here is *unpinned*: on Postgres it has no `app.tenant_id`, so
    every RLS predicate is false against it. Reads return nothing and writes are
    rejected by `WITH CHECK`, which a broad `except` then hides. The three
    sanctioned ways to obtain a session are `get_db()` (request cycle),
    `pinned_session()` (anything outside it) and `probe_session()` (a
    tenant-independent liveness probe). `test_no_unpinned_sessions_outside_request_cycle`
    fails the build on any other use, because SQLite cannot see the difference
    and a green suite therefore proved nothing.
    """
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), class_=Session, expire_on_commit=False)
    return _SessionLocal


def get_db(tenant_id: str = "") -> Generator[Session, None, None]:
    """Yield a transactional session pinned to tenant_id for RLS.

    Use as FastAPI dep via `db_for_actor` below so tenant always comes from
    the verified JWT, never from a query param.
    """
    db = _session_factory()()
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
    request/dependency cycle (middleware, SSE generators, background work,
    seeding scripts).

    Raw `_session_factory()()` is NOT safe: on Postgres the RLS `WITH CHECK` on
    tenant-scoped tables rejects the write, and a broad `except` then hides it.
    Always pin. Callers own commit/rollback/close.
    """
    db = _session_factory()()
    if tenant_id and db.bind.dialect.name == "postgresql":
        db.info[_TENANT_INFO_KEY] = tenant_id
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
    return db


def probe_session() -> Session:
    """An intentionally unpinned session, for probes that touch no tenant table.

    `GET /ready` runs `SELECT 1` and reads `alembic_version`; neither is a
    tenant-scoped table, so there is no tenant to pin and pinning one would be
    a lie about what the probe checks. This exists so the readiness probe can
    say so *without* calling the private factory and becoming the exception that
    justifies a whitelist — the previous guard exempted `routers/health.py` by
    path, which also exempted every future line added to that file.

    Callers own commit/close. Do not use this to read or write anything that has
    a `tenant_id` column.
    """
    return _session_factory()()


def rls_backstop() -> dict:
    """Ask the database whether row-level security can apply to *this* connection.

    PostgreSQL does not enforce row security for a superuser, for a role with
    `BYPASSRLS`, or for the table owner — regardless of `FORCE ROW LEVEL
    SECURITY`. Migration 0026 records that every `tenant_isolation` policy in
    this schema was a no-op from 0001 forward for exactly that reason: every
    deployment path pointed `DATABASE_URL` at the initdb superuser. The policies
    were present, `set_config` was correct, the tests on SQLite passed, and no
    rows were protected.

    The runbook states the rule ("the runtime DB role must be NON-superuser and
    must NOT own the tables") as a hard requirement. Stating it is the easy half:
    a deployment that ignores it looks identical from the outside, so this reads
    the catalog and reports whether the backstop the documentation promises is
    actually engaged.
    """
    from .config import get_settings

    url = get_settings().database_url_resolved
    if url.startswith("sqlite"):
        return {"dialect": "sqlite", "enforced": False, "applicable": False,
                "reason": "SQLite has no row-level security; tenant isolation rests on "
                          "the application's tenant filters alone"}
    if not url.startswith("postgresql"):
        return {"dialect": url.split(":", 1)[0], "enforced": False, "applicable": False,
                "reason": "unknown dialect"}

    from sqlalchemy import text

    db = probe_session()
    try:
        row = db.execute(text(
            """
            SELECT current_user AS role,
                   (SELECT coalesce(rolsuper, false) FROM pg_roles WHERE rolname = current_user) AS super,
                   (SELECT coalesce(rolbypassrls, false) FROM pg_roles WHERE rolname = current_user) AS bypass,
                   (SELECT count(*) FROM pg_tables WHERE schemaname = 'public') AS tables,
                   (SELECT count(*) FROM pg_tables WHERE schemaname = 'public'
                      AND tableowner = current_user) AS owned
            """
        )).mappings().first()
    except Exception as exc:  # noqa: BLE001 — a probe must not take the API down
        return {"dialect": "postgresql", "enforced": False, "applicable": True,
                "reason": f"could not read the catalog: {type(exc).__name__}"}
    finally:
        db.close()

    if row is None:  # pragma: no cover — defensive; the catalog query always returns a row
        return {"dialect": "postgresql", "enforced": False, "applicable": True,
                "reason": "catalog query returned no row"}

    role = str(row["role"])
    owned = int(row["owned"] or 0)
    total = int(row["tables"] or 0)
    problems: list[str] = []
    if bool(row["super"]):
        problems.append(f"{role} is a superuser")
    if bool(row["bypass"]):
        problems.append(f"{role} has BYPASSRLS")
    if total and owned == total:
        problems.append(f"{role} owns every table in public (owners bypass RLS by design)")
    enforced = not problems and bool(total)
    reason = ("row-level security applies" if enforced else
              "; ".join(problems) if problems else
              "no tables in `public` yet — nothing for the policies to protect")
    return {"dialect": "postgresql", "enforced": enforced, "applicable": True,
            "role": role, "tables": total, "owned": owned, "reason": reason}


def rls_verdict(status: dict, is_prod: bool) -> tuple[bool, str]:
    """Decide what to do about the backstop, as a function so it can be tested.

    Production refuses to start; everywhere else it is a warning. The asymmetry
    is deliberate: `vantor_app` is not a convenience, it is the difference
    between "the tenant filter was forgotten and the database caught it" and
    "the tenant filter was forgotten" — and the second case is the one this
    schema has already lived through for twenty-nine migrations.
    """
    if not status.get("applicable"):
        return True, str(status.get("reason", ""))
    if status.get("enforced"):
        return True, f"RLS enforced as role {status.get('role', '?')}"
    message = (
        "row-level security is NOT enforced for this connection: "
        f"{status.get('reason', 'unknown')}. Tenant isolation currently rests "
        "on the application's `tenant_id` filters alone. Point DATABASE_URL at "
        "the non-owner, non-superuser role created by migration 0026 "
        "(`vantor_app`), as docs/09-operations/runbook.md §7 requires."
    )
    return (not is_prod), message


def reset_engine_cache() -> None:
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None
