"""The `Vector` column type — VNT-016.

pgvector needs three things, and the one that is easiest to skip is the third:
validating the width *on the way in*. A `vector(n)` column rejects any other
width, and the write that triggers it happens in a background job, so the symptom
is chunks quietly losing their vectors rather than a visible failure.
"""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.models.vectortype import Vector, embedding_dims, validate_vector


class Base(DeclarativeBase):
    pass


class Chunk(Base):
    __tablename__ = "vtest_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(sa.String(64))
    embedding: Mapped[list[float] | None] = mapped_column(Vector, default=None, nullable=True)


@pytest.fixture()
def db() -> Session:
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_dimensions_default_and_are_configurable(monkeypatch):
    monkeypatch.delenv("EMBEDDING_DIMS", raising=False)
    assert embedding_dims() == 384

    monkeypatch.setenv("EMBEDDING_DIMS", "1536")
    assert embedding_dims() == 1536

    # Garbage falls back rather than raising: a typo in the environment must not
    # take document extraction down.
    monkeypatch.setenv("EMBEDDING_DIMS", "many")
    assert embedding_dims() == 384
    monkeypatch.setenv("EMBEDDING_DIMS", "-4")
    assert embedding_dims() == 384


def test_a_vector_round_trips_through_the_column(db: Session):
    db.add(Chunk(text="a", embedding=[0.5, 0.25, -0.125]))
    db.commit()
    db.expire_all()
    row = db.execute(sa.select(Chunk)).scalar_one()
    assert row.embedding == [0.5, 0.25, -0.125]
    assert all(isinstance(v, float) for v in row.embedding)


def test_absent_vector_stays_absent(db: Session):
    """NULL means "no vector".

    The old column stored `{}` for that, and a zero vector scores 0.0 against
    every query — so an un-embedded chunk was ranked as if it weakly matched.
    NULL cannot be confused with a vector because it is not a list.
    """
    db.add(Chunk(text="b", embedding=None))
    db.commit()
    db.expire_all()
    assert db.execute(sa.select(Chunk)).scalar_one().embedding is None


def test_an_empty_list_is_stored_as_absent(db: Session):
    db.add(Chunk(text="c", embedding=[]))
    db.commit()
    db.expire_all()
    assert db.execute(sa.select(Chunk)).scalar_one().embedding is None


def test_validate_vector_returns_none_for_no_vector():
    assert validate_vector(None) is None
    assert validate_vector([]) is None


def test_validate_vector_normalises_to_floats(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIMS", "3")
    assert validate_vector([1, 0, 1]) == [1.0, 0.0, 1.0]


def test_validate_vector_refuses_a_wrong_width(monkeypatch):
    """The check that saves a background job from failing silently."""
    monkeypatch.delenv("EMBEDDING_DIMS", raising=False)
    with pytest.raises(ValueError) as caught:
        validate_vector([0.1] * 100)
    assert "384" in str(caught.value)
    assert "EMBEDDING_DIMS" in str(caught.value)


def test_the_embedding_service_and_the_column_agree():
    """One source of truth for the width.

    These were two separate literals — 384 in the embedding service and 768 in
    the column declaration — so a provider's vectors were rejected by the column
    and every chunk silently lost its embedding. The test that would have caught
    it is this one, not a test of either constant on its own.
    """
    from app.services.embeddings import DIMS

    assert DIMS == embedding_dims()


def test_sqlite_uses_json_not_a_vector_type():
    """The portable path must keep the representation it had.

    Every test in this suite runs on SQLite, so the column has to work there or
    the whole suite becomes a PostgreSQL-only suite.
    """
    dialect = sa.create_engine("sqlite://").dialect
    rendered = str(Vector().load_dialect_impl(dialect))
    assert "JSON" in rendered.upper()
    assert "vector(" not in rendered


def test_postgresql_renders_a_sized_vector(monkeypatch):
    """The DDL that matters, asserted without needing a server.

    `sa.create_engine("postgresql://")` builds a dialect without connecting, so
    the rendered type can be checked offline. This is the part that cannot be
    verified here by running anything, so it is at least verified by asserting it.
    """
    dialect = sa.create_engine("postgresql+psycopg://").dialect

    monkeypatch.setenv("EMBEDDING_DIMS", "384")
    rendered = str(Vector().load_dialect_impl(dialect).compile(dialect=dialect))
    assert rendered == "vector(384)"

    monkeypatch.setenv("EMBEDDING_DIMS", "1536")
    rendered = str(Vector().load_dialect_impl(dialect).compile(dialect=dialect))
    assert rendered == "vector(1536)"


def test_the_postgres_bind_format_is_what_pgvector_parses(monkeypatch):
    """pgvector accepts the literal text form, not a Python list."""
    monkeypatch.setenv("EMBEDDING_DIMS", "3")
    dialect = sa.create_engine("postgresql+psycopg://").dialect
    bound = Vector().bind_processor(dialect)([1.0, 0.5, -0.25])
    assert isinstance(bound, str)
    assert bound.startswith("[") and bound.endswith("]")
    assert json.loads(bound) == [1.0, 0.5, -0.25]


def test_the_postgres_bind_refuses_a_wrong_width(monkeypatch):
    """pgvector would reject it anyway; refusing here names the real cause."""
    monkeypatch.setenv("EMBEDDING_DIMS", "384")
    dialect = sa.create_engine("postgresql+psycopg://").dialect
    with pytest.raises(ValueError) as caught:
        Vector().bind_processor(dialect)([0.0] * 8)
    assert "vector(384)" in str(caught.value)


def test_the_sqlite_bind_is_json_text():
    dialect = sa.create_engine("sqlite://").dialect
    bound = Vector().bind_processor(dialect)([1.0, 0.5])
    # A `TypeDecorator`'s bind_processor replaces the wrapped type's, so this has
    # to be serialised here. Returning the list reaches the raw driver and fails
    # with "type 'list' is not supported" — which is what happened first.
    assert isinstance(bound, str)
    assert json.loads(bound) == [1.0, 0.5]


def test_result_value_normalises_both_representations():
    """Callers must not have to know which engine answered."""
    processor = Vector().process_result_value
    assert processor("[0.1,0.2]", None) == [0.1, 0.2]
    assert processor([0.1, 0.2], None) == [0.1, 0.2]
    assert processor(None, None) is None
    assert processor("not json", None) is None


def test_0022_migration_dialect_guard_on_sqlite():
    """B-05 regression test: migration 0022 must upgrade and downgrade on non-PostgreSQL engines."""
    import importlib.util
    import pathlib
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0022_pgvector_embeddings.py"
    spec = importlib.util.spec_from_file_location("mig_0022_test", path)
    assert spec and spec.loader
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE document_chunks (id TEXT PRIMARY KEY, embedding TEXT DEFAULT '{}')"))
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        old_op = getattr(mig, "op", None)
        mig.op = op
        try:
            mig.upgrade()
            mig.downgrade()
        finally:
            mig.op = old_op

