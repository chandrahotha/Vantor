"""Alembic — idempotency key headroom.

`idempotency_keys.key` is String(128), but the middleware stores a composite
fingerprint:

    f"{method}|{path}|{Idempotency-Key header}|{sha256(body)}"

For a realistic call — `POST /api/v1/purchase-orders/{36-char-uuid}/receipts`
with a 36-character `Idempotency-Key` — that is ~168 characters. On Postgres
the insert raises `DataError: value too long`, which `IdempotencyMiddleware`
swallows by design (fail-open, never block a legitimate write). The request
therefore succeeds with **idempotency silently disabled** and no
`Idempotent-Replayed` header, and no test noticed: every test module builds the
schema with `create_all` on SQLite, which does not enforce VARCHAR length.

This is a widening only. `VARCHAR(128) -> VARCHAR(512)` is a catalog change in
Postgres (no table rewrite, no row touched), so it is safe to run against a
live database. The model and the migration are kept in step, and the middleware
now bounds the composed fingerprint as well as the header.

Revision ID: 0016_idempotency_key_width
Revises: 0015_column_headroom
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_idempotency_key_width"
down_revision = "0015_column_headroom"
branch_labels = None
depends_on = None

#: Widening only. Anything narrower would re-break the same endpoints.
KEY_WIDTH = 512


def upgrade() -> None:
    op.alter_column("idempotency_keys", "key", type_=sa.String(KEY_WIDTH),
                    existing_type=sa.String(128), existing_nullable=False)


def downgrade() -> None:
    # Narrowing is a table rewrite and will fail for any row already holding a
    # longer fingerprint — that is intentional: refuse to silently truncate the
    # fingerprint of a row that has already been used for replay matching.
    op.alter_column("idempotency_keys", "key", type_=sa.String(128),
                    existing_type=sa.String(KEY_WIDTH), existing_nullable=False)
