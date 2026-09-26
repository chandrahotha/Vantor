"""Alembic — Phase 4 Wave 2.2 sourcing (rfq/quote/award + lines) with RLS.

Revision ID: 0003_sourcing
Revises: 0002_supplier
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_sourcing"
down_revision = "0002_supplier"
branch_labels = None
depends_on = None

TABLES = ["rfqs", "rfq_lines", "quotes", "quote_lines", "awards"]


def upgrade() -> None:
    op.create_table(
        "rfqs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("category_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.UniqueConstraint("tenant_id", "code", name="uq_rfq_tenant_code"),
        sa.Index("ix_rfq_tenant_status", "tenant_id", "status"),
    )
    op.create_table(
        "rfq_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("rfq_id", sa.String(36), nullable=False, index=True),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("uom", sa.String(16), nullable=False, server_default="each"),
        sa.UniqueConstraint("tenant_id", "rfq_id", "line_no", name="uq_rfqline_tenant_rfq_no"),
        sa.Index("ix_rfqline_tenant_rfq", "tenant_id", "rfq_id"),
    )
    op.create_table(
        "quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("rfq_id", sa.String(36), nullable=False, index=True),
        sa.Column("supplier_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("total_minor", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "rfq_id", "supplier_id", name="uq_quote_tenant_rfq_sup"),
        sa.Index("ix_quote_tenant_rfq", "tenant_id", "rfq_id"),
    )
    op.create_table(
        "quote_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("quote_id", sa.String(36), nullable=False, index=True),
        sa.Column("rfq_line_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("unit_price_minor", sa.Integer, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("line_total_minor", sa.Integer, nullable=False, server_default="0"),
        sa.Index("ix_quoteline_tenant_quote", "tenant_id", "quote_id"),
    )
    op.create_table(
        "awards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("rfq_id", sa.String(36), nullable=False, index=True),
        sa.Column("quote_id", sa.String(36), nullable=False),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column("awarded_total_minor", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "rfq_id", name="uq_award_tenant_rfq"),
        sa.Index("ix_award_tenant_rfq", "tenant_id", "rfq_id"),
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
    op.drop_table("awards")
    op.drop_table("quote_lines")
    op.drop_table("quotes")
    op.drop_table("rfq_lines")
    op.drop_table("rfqs")
