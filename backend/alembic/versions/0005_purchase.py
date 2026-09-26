"""Alembic — Phase 4 Wave 2.5 purchase (req/PO/receipt/invoice/approvals) with RLS.

Revision ID: 0005_purchase
Revises: 0004_contract
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_purchase"
down_revision = "0004_contract"
branch_labels = None
depends_on = None

TABLES = ["requisitions", "requisition_lines", "purchase_orders", "purchase_order_lines",
          "receipts", "receipt_lines", "invoices", "invoice_lines", "approvals"]

_COLS = [
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
    sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
]


def upgrade() -> None:
    op.create_table("requisitions", *list(_COLS),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("requester", sa.String(256), nullable=False, server_default=""),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.UniqueConstraint("tenant_id", "code", name="uq_req_tenant_code"),
        sa.Index("ix_req_tenant_status", "tenant_id", "status"))
    op.create_table("requisition_lines", *list(_COLS),
        sa.Column("requisition_id", sa.String(36), nullable=False, index=True),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("est_price_minor", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "requisition_id", "line_no", name="uq_reql_tenant_req_no"))
    op.create_table("purchase_orders", *list(_COLS),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("supplier_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("total_minor", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_po_tenant_code"),
        sa.Index("ix_po_tenant_status", "tenant_id", "status"))
    op.create_table("purchase_order_lines", *list(_COLS),
        sa.Column("po_id", sa.String(36), nullable=False, index=True),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("unit_price_minor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("line_total_minor", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "po_id", "line_no", name="uq_pol_tenant_po_no"))
    op.create_table("receipts", *list(_COLS),
        sa.Column("po_id", sa.String(36), nullable=False, index=True),
        sa.Column("received_by", sa.String(256), nullable=False, server_default=""),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Index("ix_receipt_tenant_po", "tenant_id", "po_id"))
    op.create_table("receipt_lines", *list(_COLS),
        sa.Column("receipt_id", sa.String(36), nullable=False, index=True),
        sa.Column("po_line_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="0"),
        sa.Index("ix_receiptline_tenant_receipt", "tenant_id", "receipt_id"))
    op.create_table("invoices", *list(_COLS),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("po_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("supplier_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="received"),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("total_minor", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_inv_tenant_code"),
        sa.Index("ix_inv_tenant_status", "tenant_id", "status"))
    op.create_table("invoice_lines", *list(_COLS),
        sa.Column("invoice_id", sa.String(36), nullable=False, index=True),
        sa.Column("po_line_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="0"),
        sa.Column("unit_price_minor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("line_total_minor", sa.Integer, nullable=False, server_default="0"),
        sa.Index("ix_invline_tenant_inv", "tenant_id", "invoice_id"))
    op.create_table("approvals", *list(_COLS),
        sa.Column("resource", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="requested"),
        sa.Column("tier", sa.String(32), nullable=False, server_default="manager"),
        sa.Column("approver", sa.String(256), nullable=False, server_default=""),
        sa.Column("decided_by", sa.String(256), nullable=False, server_default=""),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Index("ix_approval_tenant_res", "tenant_id", "resource", "resource_id"))
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = current_setting('app.tenant_id', true)) "
            f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in reversed(TABLES):
        op.drop_table(table)
