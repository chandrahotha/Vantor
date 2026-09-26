"""Alembic — notifications with RLS.

Revision ID: 0014_notifications
Revises: 0013_pricecases
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014_notifications"
down_revision = "0013_pricecases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("user_sub", sa.String(256), nullable=False, server_default=""),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("link", sa.String(512), nullable=False, server_default=""),
        sa.Column("read_at", sa.String(32), nullable=False, server_default=""),
        sa.Index("ix_notif_tenant_user", "tenant_id", "user_sub"))
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON notifications")
    op.execute(
        "CREATE POLICY tenant_isolation ON notifications "
        "USING (tenant_id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON notifications")
    op.execute("ALTER TABLE notifications DISABLE ROW LEVEL SECURITY")
    op.drop_table("notifications")
