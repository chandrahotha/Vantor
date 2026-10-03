"""Postgres-backed test support.

Single source of truth for pointing a test at a real PostgreSQL. It exists
because two separate fixtures had grown their own copy of this logic, and both
copies were wrong in the same three ways — which is how the "Postgres-backed
tier" in CI came to test SQLite while reporting green:

1. **Wrong driver.** The project ships psycopg3 (`psycopg[binary]` in
   `requirements.txt`; `Settings.database_url_resolved` prescribes it). A bare
   `postgresql://` URL makes SQLAlchemy reach for psycopg2, which is not a
   dependency — so `create_engine` raised `ModuleNotFoundError`. The fixtures
   caught only `OperationalError`, so that surfaced as a test ERROR, never as a
   skip.

2. **Alembic migrated the wrong database.** `alembic/env.py` reads
   `os.getenv("DATABASE_URL", ...)` in *preference* to the URL handed to
   `Config.set_main_option`, and `conftest` sets `DATABASE_URL=sqlite://` for the
   fast suite. So `command.upgrade(cfg, "head")` built the schema on SQLite
   while the fixture announced a real Postgres. Confirmed in the run output:
   `INFO [alembic.runtime.migration] Context impl SQLiteImpl.`

3. **The app engine still pointed at SQLite.** `get_engine()` reads
   `Settings.database_url`, so even with a migrated Postgres the application
   sessions used for the test would have talked to the in-memory SQLite database.

All three are fixed here by prescribing the driver and repointing `DATABASE_URL`
at the Postgres instance for the duration of the test.

4. **Every path was relative to the current working directory.** `Config("alembic.ini")`,
   `script_location = "alembic"` and the migration walk in
   `test_the_models_links_are_exactly_the_migrated_ones` all resolved against wherever
   pytest happened to be invoked from. CI runs the fast tier from the repository root
   (`python -m pytest backend/tests -q`) and the Postgres tier from `backend/`, so the
   same helper was correct in one job and a `FileNotFoundError` in the other — and the
   test that needs no database ran in the fast tier, where it failed on the fixture
   rather than on anything it asserts. Every path is now derived from this file.
"""
from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

PG_TEST_URL = os.getenv("PG_TEST_DATABASE_URL", "").strip()

#: Password migration 0026 sets on the restricted `vantor_app` role. A fixed
#: test default keeps existing PG_TEST_DATABASE_URL-only setups working; CI
#: and docker-compose set the real value via APP_DB_PASSWORD explicitly.
APP_DB_TEST_PASSWORD = os.getenv("APP_DB_PASSWORD", "vantor-app-test-pw").strip()

#: `backend/` — derived from this file, never from the process CWD.
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def pg_engine_url() -> str:
    """The migrator (owner/superuser) URL with the driver prescribed.

    Used only for schema setup (`build_schema`) and the Alembic config — never
    for the application's own queries. See `pg_app_url`.
    """
    if PG_TEST_URL.startswith("postgresql://"):
        return PG_TEST_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    return PG_TEST_URL


def pg_app_url() -> str:
    """The restricted `vantor_app` role's URL — what the running application
    (and so the test client) actually connects as.

    Derived from the migrator URL by swapping credentials rather than adding a
    second required env var: same host/port/database, different role. Using
    the owner/superuser role here would silently defeat the entire point of
    this test tier, the same way every deployment path did before migration
    0026_app_role_least_privilege — Postgres never applies row security to a
    superuser or BYPASSRLS role, regardless of FORCE ROW LEVEL SECURITY.
    """
    url = make_url(pg_engine_url())
    # Plain str(url) masks the password as "***" (SQLAlchemy's default repr
    # safety) — render_as_string(hide_password=False) is required to get a
    # connection string that can actually authenticate.
    return url.set(username="vantor_app", password=APP_DB_TEST_PASSWORD).render_as_string(hide_password=False)


def pg_alembic_config():  # type: ignore[no-untyped-def]
    """A Config pointed at the Postgres instance for migration commands.

    Absolute paths: `alembic/env.py` resolves `script_location` against the
    process CWD, so a relative one silently migrates nothing — or raises
    `FileNotFoundError` — depending on which directory the suite was started
    from. CI starts the fast tier at the repository root and the Postgres tier
    inside `backend/`.
    """
    from alembic.config import Config

    # Migration 0026 reads APP_DB_PASSWORD directly from the environment (it
    # cannot come from the connection URL, since it is setting a *different*
    # role's password than the one `cfg` connects as).
    os.environ.setdefault("APP_DB_PASSWORD", APP_DB_TEST_PASSWORD)

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", pg_engine_url())
    return cfg


def require_postgres() -> str:
    """Skip unless a reachable Postgres is configured and connectable.

    Catches driver errors as well as connection errors: a missing DBAPI module
    is "this environment cannot run the PG tier", which is a skip, not a
    failure of the test.
    """
    if not PG_TEST_URL:
        pytest.skip("PG_TEST_DATABASE_URL is not set — point it at a Postgres instance")
    from sqlalchemy import create_engine
    from sqlalchemy.exc import SQLAlchemyError

    try:
        engine = create_engine(pg_engine_url(), connect_args={"connect_timeout": 3})
        engine.connect().close()
    except (SQLAlchemyError, ImportError) as exc:
        # SQLAlchemyError covers the connection refusal; ImportError covers a
        # missing DBAPI driver. Both mean "this environment cannot run the PG
        # tier", which is a skip, not a failure of the test.
        pytest.skip(f"Postgres unusable at {PG_TEST_URL} ({exc})")
    return pg_engine_url()


@contextlib.contextmanager
def pointed_at_postgres() -> Iterator[None]:
    """Make `DATABASE_URL` name the Postgres instance for the duration.

    Both `alembic/env.py` and `get_engine()` read `DATABASE_URL` from the
    environment, so this is what actually makes the schema and the application
    sessions agree on which database they are using.
    """
    from app.core.config import get_settings
    from app.core.tenant import reset_engine_cache

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = PG_TEST_URL
    get_settings.cache_clear()
    reset_engine_cache()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
        reset_engine_cache()


def build_schema() -> None:
    """Bring the Postgres schema to head, inside `pointed_at_postgres()`."""
    from alembic import command

    command.upgrade(pg_alembic_config(), "head")


def purge_tenant(tenant: str) -> None:
    """Delete every row belonging to one test tenant, in FK-safe order.

    Both statements need an explicit `text()`. SQLAlchemy 2.0 removed implicit
    coercion of a raw string to a textual clause and raises
    `ArgumentError: Textual SQL expression ... should be explicitly declared as
    text(...)` instead. Because that exception was raised inside the `finally`
    of the fixture, `purge_tenant` never committed a single delete, and the
    whole module-scoped database was never cleaned between tests: the next test
    then collided with the previous one's rows and failed on a 409 that had
    nothing to do with what it was testing. The failure surfaced as a product
    bug in the assertion, which is how a test-infrastructure bug spends a day
    looking like something else.

    The table list is filtered on `tenant_id` actually existing rather than
    taken from every table in the schema. `pg_tables` includes `alembic_version`,
    which has no tenant column, and the unfiltered `DELETE` raised
    `UndefinedColumn` and rolled the whole purge back — deleting nothing while
    appearing to run.

    These tests were skipped in every environment that lacked
    PG_TEST_DATABASE_URL, so nothing had exercised this path before.

    Must run through `pinned_session`, not a raw `Session(get_engine())`: the
    restricted `vantor_app` role (migration 0026) is bound by RLS like any
    other caller, so an unpinned session has no `app.tenant_id` and every
    DELETE below would silently match zero rows — not an error, just a purge
    that never purges anything, which is exactly the kind of silent no-op this
    function's own history (above) was written to stop happening again.
    `audit_events` is excluded deliberately: the restricted role has no DELETE
    on it (immutability), and test-tenant audit rows are harmless to leave
    behind.
    """
    from sqlalchemy import text

    from app.core.tenant import pinned_session

    db = pinned_session(tenant)
    try:
        tables = db.execute(text(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relkind = 'r' AND n.nspname = 'public' "
            "AND c.relname != 'audit_events' "
            "AND EXISTS (SELECT 1 FROM pg_attribute a "
            "            WHERE a.attrelid = c.oid AND a.attname = 'tenant_id')"
        )).scalars().all()
        # `reversed(tables)` assumed `pg_class`'s unordered scan happens to come
        # back in creation order — it doesn't reliably, and once this fixture
        # covered tables with real FK edges between them (suppliers <-
        # purchase_orders) a wrong-order DELETE raised ForeignKeyViolation and
        # failed the test in teardown. Retrying in passes, dropping whichever
        # tables fail this pass and trying them again next pass, is correct
        # regardless of table order or how the dependency graph changes later.
        remaining = list(tables)
        for _ in range(len(remaining) + 1):
            if not remaining:
                break
            next_remaining = []
            for table in remaining:
                savepoint = db.begin_nested()
                try:
                    db.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": tenant})
                    savepoint.commit()
                except Exception:
                    savepoint.rollback()
                    next_remaining.append(table)
            if len(next_remaining) == len(remaining):
                raise RuntimeError(
                    f"purge_tenant made no progress on {next_remaining}; a real "
                    "FK cycle or a non-FK error is blocking cleanup"
                )
            remaining = next_remaining
        db.commit()
    finally:
        db.close()
