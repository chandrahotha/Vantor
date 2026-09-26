"""Supplier scorecards — computed snapshots stored per supplier (auditable history).

POST /suppliers/{id}/scorecard {dims, weights?} → validates, scores, stores a
snapshot row (never overwrites history), updates supplier.risk_tier.
GET /suppliers/{id}/scorecard → latest snapshot or explicit empty (never fake).
"""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class SupplierScorecard(Base, TenantMixin):
    __tablename__ = "supplier_scorecards"

    supplier_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    grade: Mapped[str] = mapped_column(String(2), default="", nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    dims: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    weights: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    hard_flags: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (Index("ix_scorecard_tenant_supplier", "tenant_id", "supplier_id"),)
