"""SQLite pooling — one connection per thread, not one for all of them.

The single-container image runs on a file-backed SQLite database
(`DATABASE_URL=sqlite:////data/vantor.db`), and the in-memory SQLite the test
suite uses is a different thing entirely. Both were being given the same pool,
`StaticPool`, on the strength of a comment that said "unit-test / local only".

`StaticPool` hands out **one connection to every thread**. That is the only way
to make an in-memory SQLite database work — its contents live inside the
connection, so a second connection would be a second, empty database. But a
SQLite connection is not safe for concurrent use, so the same pool applied to a
*file-backed* database meant that concurrent requests interleaved on one
connection. The symptoms were:

    sqlite3.InterfaceError: bad parameter or other API misuse
    IndexError: tuple index out of range     (inside SQLAlchemy's row loading)

Both surfaced as 500s. The second one is the nastier of the pair, because it
is raised while SQLAlchemy is iterating a result set: the thread that owns the
cursor finds the row it expected has been consumed by another thread.

A test cannot see this by making one request. It needs concurrent requests on
a file-backed database, so that is what this module does.
"""
from __future__ import annotations

import threading

import pytest
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.tenant import get_engine, reset_engine_cache


@pytest.fixture()
def engine_for(monkeypatch, tmp_path):
    """Build an engine for a given `DATABASE_URL` and tear it down after."""
    def _build(url: str):
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        reset_engine_cache()
        engine = get_engine()
        yield engine
        engine.dispose()
        reset_engine_cache()
        get_settings.cache_clear()
    return _build


def test_in_memory_sqlite_still_shares_one_connection(engine_for):
    """In-memory SQLite is one database inside one connection.

    Every session has to see the same data, so the pool must hand out the same
    connection to all of them. `StaticPool` is the only pool that can do that;
    `QueuePool` would give each thread its own *empty* database.
    """
    for engine in engine_for("sqlite://"):
        assert isinstance(engine.pool, StaticPool)


def test_file_backed_sqlite_does_not_share_one_connection(engine_for, tmp_path):
    """A file-backed database gets a real pool, so threads do not share a connection.

    This is the single-container deployment's configuration. Sharing one
    connection across every request thread is what produced the concurrent
    `InterfaceError` and `IndexError` above.
    """
    db = tmp_path / "vantor.db"
    for engine in engine_for(f"sqlite:///{db}"):
        assert not isinstance(engine.pool, StaticPool), (
            "a file-backed SQLite database must not use StaticPool — one "
            "connection shared by every thread is not safe for concurrent use"
        )


def test_concurrent_requests_on_a_file_database_do_not_collide(engine_for, tmp_path):
    """Concurrent reads and writes on a file-backed SQLite database all succeed.

    On the shared-connection pool this fails intermittently with
    `sqlite3.InterfaceError` or `IndexError: tuple index out of range`. Here it
    is driven hard enough to be deterministic rather than flaky: eight threads,
    each opening its own session and inserting a row.
    """
    from sqlalchemy import text

    from app.models.registry import Base

    db = tmp_path / "vantor.db"
    for engine in engine_for(f"sqlite:///{db}"):
        Base.metadata.create_all(engine)

        errors: list[BaseException] = []
        barrier = threading.Barrier(8)

        def worker(n: int) -> None:
            from sqlalchemy.orm import Session

            try:
                barrier.wait(timeout=10)
                for i in range(10):
                    with Session(engine) as s:
                        s.execute(text("SELECT 1"))
                        s.execute(
                            text("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, n INTEGER)")
                        )
                        s.execute(text("INSERT INTO t (n) VALUES (:n)"), {"n": n * 100 + i})
                        s.commit()
            except BaseException as exc:  # noqa: BLE001 - recorded and re-raised below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert not errors, f"concurrent access to a file-backed SQLite database failed: {errors[:3]}"
