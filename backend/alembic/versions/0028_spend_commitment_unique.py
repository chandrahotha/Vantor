"""Alembic 0028 — the commitment ledger's uniqueness, made real.

The composite key `uq_spend_tenant_kind_po_inv` (tenant_id, kind, po_id,
invoice_id) claimed — in the model comment and in the send path's
IntegrityError handler — to enforce one commitment per PO: "A second concurrent
send of the same PO cannot double-post the commitment; the database refuses
it". It refused nothing. Migration 0018 moved the no-link sentinel from "" to
NULL, and a unique constraint treats NULLs as distinct — on PostgreSQL always,
and on SQLite too — so two rows (tenant, 'commitment', <po>, NULL) never
collide. The only guard was the workflow itself (`po.status != "approved"`
before posting), which holds only for as long as a sent PO can never return to
`approved`.

This migration adds the partial unique index the comment claimed already
existed: one commitment per (tenant, PO), carrying no nullable column, so the
claim is a database authority rather than a description of the workflow. The
`actual` shape keeps the composite key, whose `invoice_id` is non-NULL and
therefore does fire.

Both supported engines render the WHERE clause (SQLite 3.8+ partial indexes;
PostgreSQL `WHERE ...` on the index), so no dialect guard is needed — this is
not PostgreSQL-specific DDL.

Revision ID: 0028_spend_commitment_unique
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0028_spend_commitment_unique"
down_revision = "0027_remaining_status_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_spend_commitment_per_po",
        "spend_transactions",
        ["tenant_id", "po_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'commitment' AND po_id IS NOT NULL"),
        sqlite_where=sa.text("kind = 'commitment' AND po_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_spend_commitment_per_po", table_name="spend_transactions")
