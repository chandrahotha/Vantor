"""Purchase models — Phase 4 Wave 2.5 (P2P + approvals, 3-way match ready).

Requisition(+lines) → PO(+lines) → Receipt → Invoice(+lines) → Approval.
Money in integer minor units. Approval: amount-tiered (manager/finance/legal)
with explicit approver + decision; SoD: requester cannot approve own PO.
Three-way match (global procurement rule): invoice lines must match PO lines
and received quantities before approval — enforced in service, not UI text.

Link columns (`*_id`) now carry real `ForeignKey(...)` so the ORM knows them,
and every link is separately validated in `refs.py` so the same values are
checked before a write can ever reach Postgres's `RESTRICT` fails.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin

REQ_STATUSES = {"draft", "submitted", "approved", "rejected", "ordered"}
PO_STATUSES = {"draft", "approved", "sent", "received", "invoiced", "closed", "cancelled"}
INVOICE_STATUSES = {"received", "matched", "approved", "paid", "rejected"}
APPROVAL_STATUSES = {"requested", "approved", "rejected"}


class Requisition(Base, TenantMixin):
    __tablename__ = "requisitions"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    requester: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_req_tenant_code"),
        Index("ix_req_tenant_status", "tenant_id", "status"),
    )


class RequisitionLine(Base, TenantMixin):
    __tablename__ = "requisition_lines"

    requisition_id: Mapped[str] = mapped_column(String(36), ForeignKey("requisitions.id", ondelete="RESTRICT"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    est_price_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "requisition_id", "line_no", name="uq_reql_tenant_req_no"),)


class PurchaseOrder(Base, TenantMixin):
    __tablename__ = "purchase_orders"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id", ondelete="RESTRICT"), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True)
    # Link back to the requisition this PO answers. Added by 0017; NULL means a
    # PO raised without a requisition, which is legitimate and the maverick
    # report is the one thing allowed to flag it.
    requisition_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("requisitions.id", ondelete="RESTRICT"), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_po_tenant_code"),
        Index("ix_po_tenant_status", "tenant_id", "status"),
        Index("ix_po_tenant_req", "tenant_id", "requisition_id"),
    )


class PurchaseOrderLine(Base, TenantMixin):
    __tablename__ = "purchase_order_lines"

    po_id: Mapped[str] = mapped_column(String(36), ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "po_id", "line_no", name="uq_pol_tenant_po_no"),)


class Receipt(Base, TenantMixin):
    __tablename__ = "receipts"

    po_id: Mapped[str] = mapped_column(String(36), ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    received_by: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (Index("ix_receipt_tenant_po", "tenant_id", "po_id"),)


class ReceiptLine(Base, TenantMixin):
    __tablename__ = "receipt_lines"

    receipt_id: Mapped[str] = mapped_column(String(36), ForeignKey("receipts.id", ondelete="RESTRICT"), nullable=False, index=True)
    po_line_id: Mapped[str] = mapped_column(String(36), ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (Index("ix_receiptline_tenant_receipt", "tenant_id", "receipt_id"),)


class Invoice(Base, TenantMixin):
    __tablename__ = "invoices"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    po_id: Mapped[str] = mapped_column(String(36), ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="received", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id", ondelete="RESTRICT"), default="", nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_inv_tenant_code"),
        Index("ix_inv_tenant_status", "tenant_id", "status"),
    )


class InvoiceLine(Base, TenantMixin):
    __tablename__ = "invoice_lines"

    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True)
    po_line_id: Mapped[str] = mapped_column(String(36), ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_invline_tenant_inv", "tenant_id", "invoice_id"),
    )


class Approval(Base, TenantMixin):
    __tablename__ = "approvals"

    resource: Mapped[str] = mapped_column(String(64), nullable=False)  # requisition|purchase_order|invoice|ai:<resource>
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="requested", nullable=False)
    tier: Mapped[str] = mapped_column(String(32), default="manager", nullable=False)  # manager|finance|legal
    approver: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    decided_by: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (Index("ix_approval_tenant_res", "tenant_id", "resource", "resource_id"),)
