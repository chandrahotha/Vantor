"""Alembic — match runs with RLS.

Revision ID: 0011_matchruns
Revises: 0010_global_parity
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_matchruns"
down_revision = "0010_global_parity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "match_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("contract_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("po_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("invoice_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("overall", sa.String(16), nullable=False, server_default=""),
        sa.Column("hold_amount_minor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("verdict_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("cells", sa.JSON, nullable=False, server_default="[]"),
        sa.Index("ix_matchrun_tenant_po", "tenant_id", "po_id"))
    op.execute("ALTER TABLE match_runs ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON match_runs")
    op.execute(
        "CREATE POLICY tenant_isolation ON match_runs "
        "USING (tenant_id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON match_runs")
    op.execute("ALTER TABLE match_runs DISABLE ROW LEVEL SECURITY")
    op.drop_table("match_runs")
