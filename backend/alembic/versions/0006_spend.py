"""Alembic — Phase 4 Wave 2.4 spend ledger with RLS.

Revision ID: 0006_spend
Revises: 0005_purchase
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_spend"
down_revision = "0005_purchase"
branch_labels = None
depends_on = None

TABLES = ["spend_transactions", "savings_records"]


def upgrade() -> None:
    op.create_table(
        "spend_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("po_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("invoice_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("supplier_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("amount_minor", sa.Integer, nullable=False, server_default="0"),
        sa.Index("ix_spend_tenant_supplier", "tenant_id", "supplier_id"))
    op.create_table(
        "savings_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("rfq_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("award_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("saved_minor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("basis", sa.String(64), nullable=False, server_default="max-evaluated-vs-award"),
        sa.UniqueConstraint("tenant_id", "award_id", name="uq_saving_tenant_award"))
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
    op.drop_table("savings_records")
    op.drop_table("spend_transactions")
