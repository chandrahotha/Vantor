"""Document models — Phase 5 Wave 1 (upload + verify; OCR/embed land in Wave 2).

Document: immutable byte record (hash-addressed storage, tamper-evident).
DocumentChunk: text units for search/embeddings (embedding as JSON now;
native pgvector column lands with the embedding worker in Wave 2).
"""
from __future__ import annotations

from sqlalchemy import JSON, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin

DOC_STATUSES = {"uploaded", "quarantined", "ready"}


class Document(Base, TenantMixin):
    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="uploaded", nullable=False)
    resource: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "sha256", name="uq_doc_tenant_sha"),
        Index("ix_doc_tenant_resource", "tenant_id", "resource", "resource_id"),
    )


class DocumentChunk(Base, TenantMixin):
    __tablename__ = "document_chunks"

    document_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    chunk_no: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # A list of floats when a vector exists, {} when the provider was disabled
    # or the document quarantined — chunks are excluded from ranking, never
    # assigned a zero vector and reported as if they matched. Both shapes live
    # in this one JSON column, so the annotation has to admit both.
    embedding: Mapped[dict | list[float]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_chunk_tenant_doc", "tenant_id", "document_id"),)
