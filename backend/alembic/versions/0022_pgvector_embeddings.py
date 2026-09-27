"""Alembic 0022 — embeddings in a real pgvector column.

VNT-016. `document_chunks.embedding` was a `JSON` column holding a list of
floats. Similarity was then computed in Python, in the API process, after an
`ILIKE` prefilter had already reduced the table to at most 50 rows.

That is honest about what it was — the search response reports `mode`, and the
embeddings module docstring said "real cosine geometry on real stored vectors,
but not semantic" — but it is not vector search:

* every candidate is pulled across the wire, decoded from JSON, and scored, so
  the cost is O(candidates) in the API process rather than in the index;
* the prefilter is a substring match, so a chunk that means the right thing but
  does not contain the query string is unreachable — which is most of what
  semantic retrieval is for;
* the storage is roughly 30x the size of the vector, per chunk.

This moves the column to `vector(n)` and adds an HNSW index over the cosine
operator, so the ranking can happen where the data is.

The width is `EMBEDDING_DIMS`, default 768 (nomic-embed-text), read through
`app.models.vectortype.embedding_dims` so the migration, the model and the
writer cannot disagree about it. A deployment using a different model must set
that variable *before* migrating; pgvector enforces the declared width, so a
mismatch surfaces as a failed write rather than as silently wrong similarity.

Backfill
--------
Rows are converted only where the stored array has exactly the declared width:

    embedding::text::vector

would succeed for any numeric array, and a 384-dim vector in a 768-dim column is
not a vector this column can hold — pgvector rejects it at write time, from a
background job, with no context. So rows of the wrong width are left NULL
instead. NULL means "no vector", and the search path already treats that as
unrankable rather than as a zero similarity.

Downgrade returns to JSON, for the same reason: a rollback must not silently
discard the vectors, so they are converted back rather than dropped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_pgvector_embeddings"
down_revision = "0021_signature_verified_via"
branch_labels = None
depends_on = None


def _dims() -> int:
    # Imported rather than reimplemented, so the width is defined once.
    from app.models.vectortype import embedding_dims

    return embedding_dims()


def _PgVector(dims: int):  # noqa: N802 - mirrors SQLAlchemy's naming
    """The concrete `vector(n)` type for the migration's DDL.

    `sqlalchemy.UserDefinedType` is an abstract base that takes no arguments; the
    size has to be carried by a subclass implementing `get_col_spec`. The model
    has exactly that class (`app.models.vectortype._PgVector`) and it is
    imported rather than re-declared, so the migration cannot drift from the
    model it is migrating to.
    """
    from app.models.vectortype import _PgVector as _Type

    return _Type(dims)


def upgrade() -> None:
    dims = _dims()

    # pgvector is an extension, so it has to exist before the column type does.
    # IF NOT EXISTS because the image ships it enabled in some configurations and
    # this migration must be re-runnable.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # The column keeps its name. It was `JSON` holding a list of floats; the
    # model's `embedding` attribute is now typed `Vector`, which renders as
    # `vector(n)` on PostgreSQL. Adding a second column called
    # `embedding_vector` and dropping `embedding` would have left the ORM pointing
    # at a name the database no longer had - a failure at query time, in
    # production, rather than at migration time.

    # Rows whose stored array is not exactly the declared width cannot become a
    # vector this column can hold; pgvector rejects them at write time, from a
    # background job, with no context. NULL them out first so the type change
    # below cannot fail halfway. NULL means "no vector", and the search path
    # already treats that as unrankable rather than as a zero similarity.
    op.execute(
        f"""
        UPDATE document_chunks
           SET embedding = NULL
         WHERE embedding IS NOT NULL
           AND (json_typeof(embedding) <> 'array'
                OR json_array_length(embedding) <> {dims})
        """
    )

    # A JSON default of '{}' is not a valid vector, and NOT NULL contradicts the
    # NULL-means-no-vector convention the new column relies on.
    op.alter_column("document_chunks", "embedding", server_default=None)
    op.alter_column("document_chunks", "embedding", nullable=True)

    op.alter_column(
        "document_chunks", "embedding",
        type_=_PgVector(dims),
        postgresql_using="embedding::text::vector",
    )

    # HNSW over the cosine operator: the index does the ranking.
    # `vector_cosine_ops` matches the `<=>` operator used for ordering. ivfflat
    # would need a recurring REINDEX to stay accurate, which is an operational
    # cost for no benefit at this table size; HNSW does not.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunk_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw")
    op.alter_column(
        "document_chunks", "embedding",
        type_=sa.JSON(),
        postgresql_using="embedding::text::jsonb",
    )
    op.alter_column("document_chunks", "embedding", nullable=False,
                    server_default=sa.text("'{}'::jsonb"))
