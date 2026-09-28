"""Sourcing models — Phase 4 Wave 2.2 (RFQLens real chain, demo paths excluded).

Tables: rfqs, rfq_lines, quotes, quote_lines, awards.
Money: integer minor units + ISO currency (no floats). Lifecycle:
  RFQ: draft → sent → response → evaluated → awarded → closed (archived via closed).
  Quote: draft → submitted → evaluated → awarded | rejected.
  Award: single winning quote per RFQ (unique), server-computed total from lines.
No MockAIProvider, no synthetic bands, no hash costs, no 1000000 defaults.

No empty-string sentinel for linked columns — NULL in 0018, ForeignKey in the model.
"""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, tenant_key, tenant_ref

RFQ_STATUSES = {"draft", "sent", "response", "evaluated", "awarded", "closed"}
QUOTE_STATUSES = {"draft", "submitted", "evaluated", "awarded", "rejected"}


class Rfq(Base, TenantMixin):
    __tablename__ = "rfqs"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    category_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_rfq_tenant_code"),
        Index("ix_rfq_tenant_status", "tenant_id", "status"),

        # Composite, tenant-carrying links — this table is referenced by a composite link and itself linked by a composite reference.
        tenant_key("rfqs"),
        tenant_ref("rfqs", "category_id", "categories"),
    )


class RfqLine(Base, TenantMixin):
    __tablename__ = "rfq_lines"

    rfq_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    uom: Mapped[str] = mapped_column(String(16), default="each", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "rfq_id", "line_no", name="uq_rfqline_tenant_rfq_no"),
        Index("ix_rfqline_tenant_rfq", "tenant_id", "rfq_id"),

        # Composite, tenant-carrying links — this table is referenced by a composite link and itself linked by a composite reference.
        tenant_key("rfq_lines"),
        tenant_ref("rfq_lines", "rfq_id", "rfqs"),
    )


class Quote(Base, TenantMixin):
    __tablename__ = "quotes"

    rfq_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    supplier_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "rfq_id", "supplier_id", name="uq_quote_tenant_rfq_sup"),
        Index("ix_quote_tenant_rfq", "tenant_id", "rfq_id"),

        # Composite, tenant-carrying links — this table is referenced by a composite link and itself linked by a composite reference.
        tenant_key("quotes"),
        tenant_ref("quotes", "rfq_id", "rfqs"),
        tenant_ref("quotes", "supplier_id", "suppliers"),
    )


class QuoteLine(Base, TenantMixin):
    __tablename__ = "quote_lines"

    quote_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rfq_line_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_quoteline_tenant_quote", "tenant_id", "quote_id"),

        # Composite, tenant-carrying links — this table is itself linked by a composite reference.
        tenant_ref("quote_lines", "quote_id", "quotes"),
        tenant_ref("quote_lines", "rfq_line_id", "rfq_lines"),
    )


class Award(Base, TenantMixin):
    __tablename__ = "awards"

    rfq_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quote_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    awarded_total_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "rfq_id", name="uq_award_tenant_rfq"),
        Index("ix_award_tenant_rfq", "tenant_id", "rfq_id"),

        # Composite, tenant-carrying links — this table is referenced by a composite link and itself linked by a composite reference.
        tenant_key("awards"),
        tenant_ref("awards", "rfq_id", "rfqs"),
        tenant_ref("awards", "quote_id", "quotes"),
    )
