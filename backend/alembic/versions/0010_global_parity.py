"""Alembic — catalogs + budgets + signatures with RLS.

Revision ID: 0010_global_parity
Revises: 0009_scorecards
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_global_parity"
down_revision = "0009_scorecards"
branch_labels = None
depends_on = None

TABLES = ["catalog_items", "budgets", "contract_signatures"]


def upgrade() -> None:
    op.add_column("purchase_orders", sa.Column("category_id", sa.String(36), nullable=False, server_default=""))
    op.create_table(
        "catalog_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("category_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("uom", sa.String(16), nullable=False, server_default="each"),
        sa.Column("ref_price_minor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_catalog_tenant_code"),
        sa.Index("ix_catalog_tenant_cat", "tenant_id", "category_id"))
    op.create_table(
        "budgets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("category_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("ceiling_minor", sa.Integer, nullable=False),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.UniqueConstraint("tenant_id", "category_id", "period", name="uq_budget_tenant_cat_period"))
    op.create_table(
        "contract_signatures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("contract_id", sa.String(36), nullable=False, index=True),
        sa.Column("signer", sa.String(256), nullable=False),
        sa.Column("method", sa.String(16), nullable=False, server_default="internal"),
        sa.Column("provider", sa.String(64), nullable=False, server_default=""),
        sa.Column("envelope_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("snapshot_hash", sa.String(64), nullable=False, server_default=""),
        sa.Index("ix_sig_tenant_contract", "tenant_id", "contract_id"))
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = current_setting('app.tenant_id', true)) "
            f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    op.drop_column("purchase_orders", "category_id")
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("contract_signatures")
    op.drop_table("budgets")
    op.drop_table("catalog_items")
