"""Alembic — price cases with RLS.

Revision ID: 0013_pricecases
Revises: 0012_onboarding
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013_pricecases"
down_revision = "0012_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("po_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("po_line_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("supplier_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("item", sa.String(500), nullable=False, server_default=""),
        sa.Column("baseline_minor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("quoted_minor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("variance_bp", sa.Integer, nullable=False, server_default="0"),
        sa.Column("samples", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("detail", sa.JSON, nullable=False, server_default="{}"),
        sa.Index("ix_pricecase_tenant_status", "tenant_id", "status"))
    op.execute("ALTER TABLE price_cases ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON price_cases")
    op.execute(
        "CREATE POLICY tenant_isolation ON price_cases "
        "USING (tenant_id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON price_cases")
    op.execute("ALTER TABLE price_cases DISABLE ROW LEVEL SECURITY")
    op.drop_table("price_cases")
