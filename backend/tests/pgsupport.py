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

PG_TEST_URL = os.getenv("PG_TEST_DATABASE_URL", "").strip()

#: `backend/` — derived from this file, never from the process CWD.
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def pg_engine_url() -> str:
    """The test URL with the driver prescribed, matching the app's resolution."""
    if PG_TEST_URL.startswith("postgresql://"):
        return PG_TEST_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    return PG_TEST_URL


def pg_alembic_config():  # type: ignore[no-untyped-def]
    """A Config pointed at the Postgres instance for migration commands.

    Absolute paths: `alembic/env.py` resolves `script_location` against the
    process CWD, so a relative one silently migrates nothing — or raises
    `FileNotFoundError` — depending on which directory the suite was started
    from. CI starts the fast tier at the repository root and the Postgres tier
    inside `backend/`.
    """
    from alembic.config import Config

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
    """
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from app.core.tenant import get_engine

    db = Session(get_engine())
    try:
        tables = db.execute(text(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relkind = 'r' AND n.nspname = 'public' "
            "AND EXISTS (SELECT 1 FROM pg_attribute a "
            "            WHERE a.attrelid = c.oid AND a.attname = 'tenant_id')"
        )).scalars().all()
        for table in reversed(tables):
            db.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": tenant})
        db.commit()
    finally:
        db.close()
