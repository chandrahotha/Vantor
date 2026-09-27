"""Spend models — Phase 4 Wave 2.4 (real aggregates, no fixtures).

spend_transactions: immutable ledger rows written server-side on PO send
(commitment) and invoice approval (actuals). savings_records: award savings
(winning vs highest evaluated total) written on award. Dashboards aggregate
from these rows — empty states when no data, never synthetic numbers.
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin


class SpendTransaction(Base, TenantMixin):
    __tablename__ = "spend_transactions"

    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # commitment|actual
    po_id: Mapped[str] = mapped_column(String(36), ForeignKey("purchase_orders.id", ondelete="RESTRICT"), default="", nullable=False)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="RESTRICT"), default="", nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # VNT-027. The ledger's uniqueness used to live only in the workflow: a
    # commitment was written because the PO read `approved`, an actual because
    # the invoice read `received`. Both reads are unlocked, so two concurrent
    # sends (or approvals) of the same document each saw the pre-state and each
    # wrote a row — double-counting the same money in every aggregate.
    #
    # One composite key covers both shapes without a partial index:
    #   - commitment -> (tenant, "commitment", <po>, "")  : one per PO
    #   - actual     -> (tenant, "actual", <po>, <inv>)   : one per invoice
    # Two different invoices against the same PO carry different `invoice_id`
    # and so do not collide, which is exactly right for partial invoicing.
    __table_args__ = (
        Index("ix_spend_tenant_supplier", "tenant_id", "supplier_id"),
        UniqueConstraint("tenant_id", "kind", "po_id", "invoice_id", name="uq_spend_tenant_kind_po_inv"),
        CheckConstraint("kind in ('commitment','actual')", name="ck_spend_kind"),
        CheckConstraint("amount_minor >= 0", name="ck_spend_amount_nonneg"),
        CheckConstraint("(currency = '' OR length(currency) = 3)", name="ck_spend_currency_iso3"),
    )


class SavingsRecord(Base, TenantMixin):
    __tablename__ = "savings_records"

    rfq_id: Mapped[str] = mapped_column(String(36), ForeignKey("rfqs.id", ondelete="RESTRICT"), default="", nullable=False)
    award_id: Mapped[str] = mapped_column(String(36), ForeignKey("awards.id", ondelete="RESTRICT"), default="", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    saved_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    basis: Mapped[str] = mapped_column(String(64), default="max-evaluated-vs-award", nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "award_id", name="uq_saving_tenant_award"),
                      CheckConstraint("saved_minor >= 0", name="ck_saving_nonneg"),
                      CheckConstraint("(currency = '' OR length(currency) = 3)", name="ck_saving_currency_iso3"))
