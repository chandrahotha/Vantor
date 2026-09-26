"""Alembic — column headroom + per-recipient notification read state.

Three fixes, all of which are 500s on Postgres that pass silently on SQLite
(which enforces neither length nor the RLS backstop):

1. `approvals.resource` was String(32) but the HITL tool files `ai:<resource>`,
   so a 30-char caller-supplied resource overflowed the column on commit.
2. `notifications.read_at` was String(32) and stores
   `datetime.now(timezone.utc).isoformat()`, which is *exactly* 32 characters.
   Any format change (Z suffix, microsecond precision) was one commit away from
   a 500 on the most common user action in the product: marking a row read.
3. Broadcast notifications (`user_sub=""`) are one row shared by the whole
   tenant, so `read_at` meant "somebody read it" and the first reader silenced
   the alert for everyone. `read_by` carries per-recipient state instead.

Revision ID: 0015_column_headroom
Revises: 0014_notifications
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_column_headroom"
down_revision = "0014_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("approvals", "resource", type_=sa.String(64),
                    existing_type=sa.String(32), existing_nullable=False)
    op.alter_column("notifications", "read_at", type_=sa.String(40),
                    existing_type=sa.String(32), existing_nullable=False)
    op.add_column("notifications", sa.Column("read_by", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("notifications", "read_by")
    op.alter_column("notifications", "read_at", type_=sa.String(32),
                    existing_type=sa.String(40), existing_nullable=False)
    op.alter_column("approvals", "resource", type_=sa.String(32),
                    existing_type=sa.String(64), existing_nullable=False)

