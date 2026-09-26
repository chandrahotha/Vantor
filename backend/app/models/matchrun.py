"""Match runs — stored, hash-linked evaluation records (evidence for awards/disputes)."""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class MatchRun(Base, TenantMixin):
    __tablename__ = "match_runs"

    contract_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    po_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    invoice_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    overall: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    hold_amount_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verdict_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    cells: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (Index("ix_matchrun_tenant_po", "tenant_id", "po_id"),)
