"""Alembic — Phase 4 Wave 2.3 contracts + obligations with RLS.

Revision ID: 0004_contract
Revises: 0003_sourcing
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_contract"
down_revision = "0003_sourcing"
branch_labels = None
depends_on = None

TABLES = ["contracts", "contract_obligations"]


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("supplier_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("contract_type", sa.String(64), nullable=False, server_default="supply"),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("value_minor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("start_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("end_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.UniqueConstraint("tenant_id", "code", name="uq_contract_tenant_code"),
        sa.Index("ix_contract_tenant_status", "tenant_id", "status"),
        sa.Index("ix_contract_tenant_end", "tenant_id", "end_date"),
    )
    op.create_table(
        "contract_obligations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("contract_id", sa.String(36), nullable=False, index=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("due_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("owner", sa.String(200), nullable=False, server_default=""),
        sa.Index("ix_oblig_tenant_contract", "tenant_id", "contract_id"),
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
    op.drop_table("contract_obligations")
    op.drop_table("contracts")
