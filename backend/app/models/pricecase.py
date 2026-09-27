"""Price anomaly cases — persistent workflow rows (open → handed_off | dismissed)."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class PriceCase(Base, TenantMixin):
    __tablename__ = "price_cases"

    po_id: Mapped[str] = mapped_column(String(36), ForeignKey("purchase_orders.id", ondelete="RESTRICT"), default="", nullable=False)
    po_line_id: Mapped[str] = mapped_column(String(36), ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), default="", nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id", ondelete="RESTRICT"), default="", nullable=False)
    item: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    baseline_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quoted_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    variance_bp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    samples: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_pricecase_tenant_status", "tenant_id", "status"),)
