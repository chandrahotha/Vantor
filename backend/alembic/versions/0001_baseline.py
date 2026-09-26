"""Alembic baseline — Phase 3 Foundation.

Creates: pgvector extension, organizations, user_accounts, roles,
audit_events (immutable, hash-chained), idempotency_keys.
Enforces tenant RLS on every table: tenant_id = current_setting('app.tenant_id').

Revision ID: 0001_baseline
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = ["organizations", "user_accounts", "roles", "audit_events", "idempotency_keys"]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_org_tenant_slug"),
    )
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("subject", sa.String(256), nullable=False),
        sa.Column("email", sa.String(320), nullable=False, server_default=""),
        sa.Column("display_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("roles", sa.JSON, nullable=False, server_default="[]"),
        sa.UniqueConstraint("tenant_id", "subject", name="uq_user_tenant_sub"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("permissions", sa.JSON, nullable=False, server_default="[]"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("actor", sa.String(256), nullable=False),
        sa.Column("action", sa.String(64), nullable=False, index=True),
        sa.Column("resource", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(64), nullable=False, server_default=""),
        sa.Column("before", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("after", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column("approval", sa.String(128), nullable=False, server_default=""),
        sa.Column("source", sa.String(64), nullable=False, server_default="api"),
        sa.Column("prev_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Index("ix_audit_tenant_time", "tenant_id", "occurred_at"),
        sa.Index("ix_audit_tenant_action", "tenant_id", "action"),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False, server_default="200"),
        sa.Column("response_body", sa.JSON, nullable=False, server_default="{}"),
        sa.UniqueConstraint("tenant_id", "key", "method", "path", name="uq_idem_tenant_key"),
    )
    # RLS: fail-closed — no tenant context => no rows.
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = current_setting('app.tenant_id', true)) "
            f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )
    # Audit immutability note: revoke UPDATE/DELETE in prod via dedicated migrator role.
    # GRANT SELECT, INSERT ON audit_events TO vantor_app; (applied by ops, not here)


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("idempotency_keys")
    op.drop_table("audit_events")
    op.drop_table("roles")
    op.drop_table("user_accounts")
    op.drop_table("organizations")
