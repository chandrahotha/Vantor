"""Catalog + budgets + signatures — global-parity models (Ariba/Coupa/Ivalua checklist).

CatalogItem: buyer-managed purchasables (guided buying) that prefill
requisition/PO lines with validated UOM + reference prices. No spot-buy fakery:
every line still validates against supplier + budget rules downstream.

Budget: per (category_id, period YYYY-MM) ceiling in minor units. PO approval
performs a hard check: sum(approved+sent POs' lines in scope) + this PO must fit.
Over-budget => 422 with the numbers (never silent squeeze).

ContractSignature: sign-off records. Internal method = authenticated user click
(actor + timestamp + hash of contract snapshot). External e-sign providers plug
in via the integrations adapter interface (integrations.itype=email/notify or a
dedicated esign adapter); the record stores provider + envelope id for audit.
"""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class CatalogItem(Base, TenantMixin):
    __tablename__ = "catalog_items"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    category_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    uom: Mapped[str] = mapped_column(String(16), default="each", nullable=False)
    ref_price_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_catalog_tenant_code"),
        Index("ix_catalog_tenant_cat", "tenant_id", "category_id"),
    )


class Budget(Base, TenantMixin):
    __tablename__ = "budgets"

    category_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    ceiling_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "category_id", "period", name="uq_budget_tenant_cat_period"),)


class ContractSignature(Base, TenantMixin):
    __tablename__ = "contract_signatures"

    contract_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    signer: Mapped[str] = mapped_column(String(256), nullable=False)
    method: Mapped[str] = mapped_column(String(16), default="internal", nullable=False)  # internal|esign
    provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    envelope_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    __table_args__ = (Index("ix_sig_tenant_contract", "tenant_id", "contract_id"),)
