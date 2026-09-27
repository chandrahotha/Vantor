"""A `pgvector` column that also works on SQLite.

VNT-016. Embeddings were stored in a JSON column as a list of floats, and
similarity was computed in Python after an `ILIKE` prefilter. That is honest
about what it is - the module docstring said so, and the search response reports
`mode` - but it is not vector search: every candidate has to be pulled into the
application, decoded, and scored, so the work is O(candidates) in the API process
and no index can help.

pgvector wants three things this module provides:

* a column type that renders `VECTOR(n)` on PostgreSQL and `JSON` elsewhere, so
  the same model serves both engines and the SQLite test tier keeps working;
* a bind processor that sends a Python list as the `'[0.1,0.2]'` literal pgvector
  parses, and a result processor that turns the returned string back into a list;
* **dimension validation**, which is the part that is easy to skip and expensive
  to skip. pgvector enforces the declared width, so a provider that returns 384
  dims for a 768-dim column makes the *write* fail - and the write happens in a
  background job, so the symptom is chunks silently losing their vectors rather
  than a visible error. Validating on the way in turns that into a named error at
  the point the vector was produced.

The dimension is configuration, not a constant: `EMBEDDING_DIMS`, defaulting to
768 (nomic-embed-text). A deployment using a different model sets it, and the
migration is written against the same value.
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from sqlalchemy.types import TypeDecorator, UserDefinedType


def embedding_dims() -> int:
    """The configured vector width.

    Read per call rather than cached at import: tests and deployments both change
    it, and a value frozen at import time would be a constant that disagrees with
    the environment.

    The default is 384, which is what `services/embeddings.py` has always used and
    what its deterministic `toy` provider produces. It is deliberately the *same*
    function the embedding service uses, because a column declared `vector(768)`
    next to a provider that emits 384 dims rejects every write - and the write
    happens in a background job, so the symptom is chunks quietly losing their
    vectors rather than a visible error. (The old comment here claimed 384 was
    "nomic-embed-text dim"; that model is in fact 768. The number is this
    project's choice, not the model's, and is now stated as such.)
    """
    import os

    raw = os.getenv("EMBEDDING_DIMS", "384").strip()
    try:
        value = int(raw)
    except ValueError:
        return 384
    return value if value > 0 else 384


class _PgVector(UserDefinedType):
    """The concrete `vector(n)` type.

    `UserDefinedType` itself takes no arguments — it is an abstract base to
    subclass, and `get_col_spec` is what SQLAlchemy calls to render the type in
    DDL. Passing the size to the base class raises `TypeError`, which on
    PostgreSQL would surface only when the migration or a `create_all` compiled
    the DDL.
    """

    cache_ok = True

    def __init__(self, dims: int):
        self.dims = dims

    def get_col_spec(self, **_kw):  # type: ignore[no-untyped-def]
        return f"vector({self.dims})"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"_PgVector({self.dims})"


class Vector(TypeDecorator):
    """`vector(n)` on PostgreSQL, JSON everywhere else.

    `impl` is JSON rather than a string so the SQLite and non-PG paths keep the
    exact representation they had before, which means the portable search path
    and its tests are unaffected by this existing.
    """

    cache_ok = True
    impl = sa.JSON

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PgVector(embedding_dims()))
        return dialect.type_descriptor(sa.JSON())

    def bind_processor(self, dialect):  # type: ignore[no-untyped-def]
        def process(value):  # type: ignore[no-untyped-def]
            if value is None:
                return None
            values = list(value)
            if not values:
                return None
            if dialect.name == "postgresql":
                expected = embedding_dims()
                if len(values) != expected:
                    # Refused here rather than at the database, where the failure
                    # would surface from a background job with no context.
                    raise ValueError(
                        f"embedding has {len(values)} dimensions, column is "
                        f"vector({expected}); set EMBEDDING_DIMS to match the model"
                    )
                return "[" + ",".join(repr(float(v)) for v in values) + "]"
            # A `TypeDecorator`'s `bind_processor` *replaces* the wrapped type's,
            # so the JSON serialisation has to be done here. Returning the list
            # unchanged reaches the raw driver and fails with
            # "type 'list' is not supported" — which is exactly what happened the
            # first time, and is why this comment is here.
            return json.dumps(values)
        return process

    def process_result_value(self, value, dialect):  # type: ignore[no-untyped-def]
        """Normalise both representations to a Python list of floats.

        pgvector returns the literal text `'[0.1,0.2]'`; the JSON path returns a
        list. Callers should not have to know which engine answered.
        """
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return [float(v) for v in value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, list):
                return [float(v) for v in parsed]
        return None


def validate_vector(value: list[float] | None) -> list[float] | None:
    """Normalise a provider's vector, or return None if it is unusable.

    Returns None rather than raising for "no vector", because a chunk without one
    is a legitimate state (the provider is disabled, or failed) and the search
    path must not rank those as if they matched. A vector of the *wrong size* is
    a different thing: that is a misconfiguration and raises, because silently
    storing it would produce vectors that can never be compared correctly.
    """
    if value is None:
        return None
    values = [float(v) for v in value]
    if not values:
        return None
    expected = embedding_dims()
    if len(values) != expected:
        raise ValueError(
            f"embedding has {len(values)} dimensions, expected {expected}; "
            f"set EMBEDDING_DIMS to match the model in use"
        )
    return values
