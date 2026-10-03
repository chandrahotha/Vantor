"""Document models — Phase 5 Wave 1 (upload + verify; OCR/embed land in Wave 2).

Document: immutable byte record (hash-addressed storage, tamper-evident).
DocumentChunk: text units for search/embeddings (embedding as JSON now;
native pgvector column lands with the embedding worker in Wave 2).
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, tenant_key, tenant_ref
from .vectortype import Vector

DOC_STATUSES = {"uploaded", "quarantined", "ready"}


def _in(column: str, allowed: set[str]) -> str:
    """Render a status-domain CHECK from the single source of truth.

    RA-008 (re-audit 2026-10-02). Same pattern as
    `app/models/purchase.py::_in`: sorted so the DDL string is byte-identical
    on every build, matching what
    `alembic/versions/0027_remaining_status_checks.py` creates.
    """
    values = ", ".join(f"'{s}'" for s in sorted(allowed))
    return f"{column} in ({values})"


class Document(Base, TenantMixin):
    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="uploaded", nullable=False)
    resource: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "sha256", name="uq_doc_tenant_sha"),
        Index("ix_doc_tenant_resource", "tenant_id", "resource", "resource_id"),
        CheckConstraint(_in("status", DOC_STATUSES), name="ck_document_status"),

        # Composite, tenant-carrying link — this table is referenced by a composite link.
        tenant_key("documents"),
    )


class DocumentChunk(Base, TenantMixin):
    __tablename__ = "document_chunks"

    document_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    chunk_no: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # VNT-016. Was a bare JSON column holding a list of floats, with similarity
    # computed in Python after an ILIKE prefilter. It renders as `vector(n)` on
    # PostgreSQL - so the index can do the work and the API process does not have
    # to pull every candidate across the wire to score it - and as JSON on
    # SQLite, so the portable search path and its tests are unchanged.
    #
    # A chunk with no vector is NULL, not a zero vector. `{}` was the old
    # "absent" marker and a zero vector scores 0.0 against every query, which
    # would rank an un-embedded chunk as if it weakly matched.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector, default=None, nullable=True
    )

    __table_args__ = (
        Index("ix_chunk_tenant_doc", "tenant_id", "document_id"),
        # The HNSW index the vector search actually rides on, declared so the
        # model and the migrated schema agree. `postgresql_using`/`postgresql_ops`
        # keep it a no-op on SQLite, which has no operator class for `vector`.
        # 0022 creates exactly this index; without it here, every
        # `test_database_matches_metadata` run reported a phantom
        # `remove_index` and the ORM could not be used to build a fresh
        # database with the index the embedding worker relies on.
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Composite, tenant-carrying links — this table is itself linked by a composite reference.
        tenant_ref("document_chunks", "document_id", "documents"),
    )
