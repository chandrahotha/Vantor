"""Alembic — Phase 8 Wave 1 integrations + webhooks with RLS.

Revision ID: 0008_integrations
Revises: 0007_documents
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_integrations"
down_revision = "0007_documents"
branch_labels = None
depends_on = None

TABLES = ["integrations", "webhook_endpoints", "webhook_deliveries"]


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("itype", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="disabled"),
        sa.Column("settings", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("secret_ref", sa.String(256), nullable=False, server_default=""),
        sa.Index("ix_integration_tenant_type", "tenant_id", "itype"))
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("events", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("secret_ref", sa.String(256), nullable=False, server_default=""),
        sa.Index("ix_hook_tenant_url", "tenant_id", "url"))
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("endpoint_id", sa.String(36), nullable=False, index=True),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=False, server_default=""),
        sa.Index("ix_delivery_tenant_endpoint", "tenant_id", "endpoint_id"))
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
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
    op.drop_table("integrations")
