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

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, tenant_key, tenant_ref

REQ_STATUSES = {"draft", "submitted", "approved", "rejected", "ordered"}
PO_STATUSES = {"draft", "approved", "sent", "received", "invoiced", "closed", "cancelled"}
INVOICE_STATUSES = {"received", "matched", "approved", "paid", "rejected"}
APPROVAL_STATUSES = {"requested", "approved", "rejected"}

TIER_STATUSES = {"manager", "finance", "legal"}


def _in(column: str, allowed: set[str]) -> str:
    """Render a status-domain CHECK from the single source of truth.

    VNT-028: these four sets were module-level literals that *nothing imported*.
    The state machines in the workkit described transitions, the routers
    enforced them in Python, and the database would have happily stored
    `"banana"` in `purchase_orders.status` — after which every read path 422s
    on a value no code could have written through the API. Rendering the CHECK
    from the same set means the domain and the constraint cannot drift.

    Sorted so the DDL string is byte-identical on every build; `alembic check`
    compares the rendered string, and an unsorted set would make it flap.
    """
    values = ", ".join(f"'{s}'" for s in sorted(allowed))
    return f"{column} in ({values})"


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
        CheckConstraint(_in("status", REQ_STATUSES), name="ck_requisition_status"),

        # Composite, tenant-carrying link — this table is referenced by a composite link.
        tenant_key("requisitions"),
    )


class RequisitionLine(Base, TenantMixin):
    __tablename__ = "requisition_lines"

    requisition_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    est_price_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "requisition_id", "line_no", name="uq_reql_tenant_req_no"),
                      CheckConstraint("quantity > 0", name="ck_reql_qty_pos"),

        # Composite, tenant-carrying links — this table is itself linked by a composite reference.
        tenant_ref("requisition_lines", "requisition_id", "requisitions"),
                      CheckConstraint("est_price_minor >= 0", name="ck_reql_price_nonneg"))


class PurchaseOrder(Base, TenantMixin):
    __tablename__ = "purchase_orders"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    category_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Link back to the requisition this PO answers. Added by 0017; NULL means a
    # PO raised without a requisition, which is legitimate and the maverick
    # report is the one thing allowed to flag it.
    requisition_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_po_tenant_code"),
        Index("ix_po_tenant_status", "tenant_id", "status"),
        Index("ix_po_tenant_req", "tenant_id", "requisition_id"),
        CheckConstraint(_in("status", PO_STATUSES), name="ck_po_status"),
        CheckConstraint("total_minor >= 0", name="ck_po_total_nonneg"),

        # Composite, tenant-carrying links — this table is referenced by a composite link and itself linked by a composite reference.
        tenant_key("purchase_orders"),
        tenant_ref("purchase_orders", "supplier_id", "suppliers"),
        tenant_ref("purchase_orders", "category_id", "categories"),
        tenant_ref("purchase_orders", "requisition_id", "requisitions"),
    )


class PurchaseOrderLine(Base, TenantMixin):
    __tablename__ = "purchase_order_lines"

    po_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "po_id", "line_no", name="uq_pol_tenant_po_no"),
                      CheckConstraint("quantity > 0", name="ck_pol_qty_pos"),
                      CheckConstraint("unit_price_minor > 0", name="ck_pol_price_pos"),

        # Composite, tenant-carrying links — this table is referenced by a composite link and itself linked by a composite reference.
        tenant_key("purchase_order_lines"),
        tenant_ref("purchase_order_lines", "po_id", "purchase_orders"),
                      CheckConstraint("line_total_minor = unit_price_minor * quantity", name="ck_pol_line_math"))


class Receipt(Base, TenantMixin):
    __tablename__ = "receipts"

    po_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    received_by: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        Index("ix_receipt_tenant_po", "tenant_id", "po_id"),

        # Composite, tenant-carrying links — this table is referenced by a composite link and itself linked by a composite reference.
        tenant_key("receipts"),
        tenant_ref("receipts", "po_id", "purchase_orders"),
    )


class ReceiptLine(Base, TenantMixin):
    __tablename__ = "receipt_lines"

    receipt_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    po_line_id: Mapped[str] = mapped_column(String(36), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (Index("ix_receiptline_tenant_receipt", "tenant_id", "receipt_id"),

        # Composite, tenant-carrying links — this table is itself linked by a composite reference.
        tenant_ref("receipt_lines", "receipt_id", "receipts"),
        tenant_ref("receipt_lines", "po_line_id", "purchase_order_lines"),
                      CheckConstraint("quantity > 0", name="ck_receiptline_qty_pos"))


class Invoice(Base, TenantMixin):
    __tablename__ = "invoices"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    # `index=True` removed: the migrated schema has no `ix_invoices_po_id`, and
    # a single-column index here is exactly the thing the composite link makes
    # unnecessary. Declaring one the database does not have is not a harmless
    # extra — it is a diff, so it made `test_database_matches_metadata` fail on
    # every run for a column that is already indexed by
    # `ix_invoice_tenant_po` on the tenant-scoped access path.
    po_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="received", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_inv_tenant_code"),
        Index("ix_inv_tenant_status", "tenant_id", "status"),
        CheckConstraint(_in("status", INVOICE_STATUSES), name="ck_invoice_status"),
        CheckConstraint("total_minor > 0", name="ck_invoice_total_pos"),
        CheckConstraint("(currency = '' OR length(currency) = 3)", name="ck_invoice_currency_iso3"),

        # Composite, tenant-carrying links — this table is referenced by a composite link and itself linked by a composite reference.
        tenant_key("invoices"),
        tenant_ref("invoices", "po_id", "purchase_orders"),
        tenant_ref("invoices", "supplier_id", "suppliers"),
    )


class InvoiceLine(Base, TenantMixin):
    __tablename__ = "invoice_lines"

    invoice_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    po_line_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_invline_tenant_inv", "tenant_id", "invoice_id"),
        CheckConstraint("quantity > 0", name="ck_invline_qty_pos"),
        CheckConstraint("unit_price_minor > 0", name="ck_invline_price_pos"),
        CheckConstraint("line_total_minor = unit_price_minor * quantity", name="ck_invline_line_math"),

        # Composite, tenant-carrying links — this table is itself linked by a composite reference.
        tenant_ref("invoice_lines", "invoice_id", "invoices"),
        tenant_ref("invoice_lines", "po_line_id", "purchase_order_lines"),
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

    __table_args__ = (Index("ix_approval_tenant_res", "tenant_id", "resource", "resource_id"),
                      CheckConstraint(_in("status", APPROVAL_STATUSES), name="ck_approval_status"),
                      CheckConstraint(_in("tier", TIER_STATUSES), name="ck_approval_tier"),
                      # One approval per (resource, resource_id, tier). The tier
                      # ordering rule assumes exactly one outstanding slot per
                      # tier; without this, two files of the same tier both
                      # return from `order_pending` and the queue is ambiguous.
                      UniqueConstraint("tenant_id", "resource", "resource_id", "tier",
                                       name="uq_approval_tenant_res_tier"))
