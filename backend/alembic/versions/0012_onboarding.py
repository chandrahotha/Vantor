"""Alembic — onboarding (certs + qualifications) with RLS.

Revision ID: 0012_onboarding
Revises: 0011_matchruns
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_onboarding"
down_revision = "0011_matchruns"
branch_labels = None
depends_on = None

TABLES = ["supplier_certifications", "supplier_qualifications"]


def upgrade() -> None:
    op.create_table(
        "supplier_certifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("supplier_id", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("issuer", sa.String(200), nullable=False, server_default=""),
        sa.Column("valid_until", sa.String(10), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("document_id", sa.String(36), nullable=False, server_default=""),
        sa.Index("ix_cert_tenant_supplier", "tenant_id", "supplier_id"))
    op.create_table(
        "supplier_qualifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("supplier_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("checklist", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("decided_by", sa.String(256), nullable=False, server_default=""),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.UniqueConstraint("tenant_id", "supplier_id", name="uq_qual_tenant_supplier"))
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
    op.drop_table("supplier_qualifications")
    op.drop_table("supplier_certifications")
