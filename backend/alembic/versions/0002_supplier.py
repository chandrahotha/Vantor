"""Alembic — Phase 4 Wave 2.1 suppliers + categories + contacts with RLS.

Revision ID: 0002_supplier
Revises: 0001_baseline
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_supplier"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

TABLES = ["categories", "suppliers", "supplier_contacts"]


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("parent_id", sa.String(36), nullable=False, server_default=""),
        sa.UniqueConstraint("tenant_id", "code", name="uq_cat_tenant_code"),
    )
    op.create_table(
        "suppliers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("country", sa.String(2), nullable=False, server_default=""),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("category_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("payment_terms", sa.String(120), nullable=False, server_default=""),
        sa.Column("risk_tier", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("source_repo", sa.String(64), nullable=False, server_default=""),
        sa.Column("source_commit", sa.String(64), nullable=False, server_default=""),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.UniqueConstraint("tenant_id", "code", name="uq_supplier_tenant_code"),
        sa.Index("ix_supplier_tenant_status", "tenant_id", "status"),
        sa.Index("ix_supplier_tenant_name", "tenant_id", "name"),
    )
    op.create_table(
        "supplier_contacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("supplier_id", sa.String(36), nullable=False, index=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False, server_default=""),
        sa.Column("phone", sa.String(64), nullable=False, server_default=""),
        sa.Column("role", sa.String(120), nullable=False, server_default=""),
        sa.Index("ix_contact_tenant_supplier", "tenant_id", "supplier_id"),
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = current_setting('app.tenant_id', true)) "
            f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("supplier_contacts")
    op.drop_table("suppliers")
    op.drop_table("categories")
