"""Spend models — Phase 4 Wave 2.4 (real aggregates, no fixtures).

spend_transactions: immutable ledger rows written server-side on PO send
(commitment) and invoice approval (actuals). savings_records: award savings
(winning vs highest evaluated total) written on award. Dashboards aggregate
from these rows — empty states when no data, never synthetic numbers.
"""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class SpendTransaction(Base, TenantMixin):
    __tablename__ = "spend_transactions"

    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # commitment|actual
    po_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    invoice_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (Index("ix_spend_tenant_supplier", "tenant_id", "supplier_id"),)


class SavingsRecord(Base, TenantMixin):
    __tablename__ = "savings_records"

    rfq_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    award_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    saved_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    basis: Mapped[str] = mapped_column(String(64), default="max-evaluated-vs-award", nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "award_id", name="uq_saving_tenant_award"),)
