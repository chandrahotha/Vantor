"""Price anomaly cases — persistent workflow rows (open → handed_off | dismissed)."""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, JSON, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, tenant_ref


class PriceCase(Base, TenantMixin):
    __tablename__ = "price_cases"

    po_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    po_line_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    item: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    baseline_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quoted_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    variance_bp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    samples: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_pricecase_tenant_status", "tenant_id", "status"),
        # At most one OPEN case per PO line, enforced by the database.
        # `/spend/price-cases` used to read the open cases and then insert, with
        # no lock and no constraint: two concurrent evaluations both saw no open
        # case for the same line and both opened one. The read-then-write is
        # inherent to the endpoint (it evaluates a whole PO in one pass), so the
        # interlock has to live where the arbitration can be atomic — which is
        # the index, not the application.
        #
        # `po_line_id <> ''` is part of the predicate, not decoration: the column
        # defaults to the empty string for cases raised without a specific line,
        # and without that clause every such open case in a tenant would collide
        # with the first one.
        Index(
            "uq_pricecase_one_open_per_line",
            "tenant_id", "po_line_id",
            unique=True,
            postgresql_where=text("status = 'open' AND po_line_id <> ''"),
            sqlite_where=text("status = 'open' AND po_line_id <> ''"),
        ),
        # Composite, tenant-carrying links — constrained in 0024. A price case is
        # a claim about a specific purchase order, its line, and a supplier, and
        # none of those references was checked by the database, so the row could
        # name a document from another tenant.
        tenant_ref("price_cases", "po_id", "purchase_orders"),
        tenant_ref("price_cases", "po_line_id", "purchase_order_lines"),
        tenant_ref("price_cases", "supplier_id", "suppliers"),
    )
