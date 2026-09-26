"""Alembic — supplier scorecards with RLS.

Revision ID: 0009_scorecards
Revises: 0008_integrations
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_scorecards"
down_revision = "0008_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_scorecards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("supplier_id", sa.String(36), nullable=False, index=True),
        sa.Column("score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("grade", sa.String(2), nullable=False, server_default=""),
        sa.Column("risk_tier", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("dims", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("weights", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("hard_flags", sa.Integer, nullable=False, server_default="0"),
        sa.Index("ix_scorecard_tenant_supplier", "tenant_id", "supplier_id"))
    op.execute("ALTER TABLE supplier_scorecards ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON supplier_scorecards")
    op.execute(
        "CREATE POLICY tenant_isolation ON supplier_scorecards "
        "USING (tenant_id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON supplier_scorecards")
    op.execute("ALTER TABLE supplier_scorecards DISABLE ROW LEVEL SECURITY")
    op.drop_table("supplier_scorecards")
