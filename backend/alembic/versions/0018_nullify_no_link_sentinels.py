"""Alembic — "no link" sentinel "" becomes NULL.

Every column below received an official "" sentinel because the schema has no
FKs, and "" was the only safe no-link value. A FOREIGN KEY cannot express "".
NULL is the answer SQL gives without inventing a magic string.

For each column:
    1. ``UPDATE … SET col = NULL WHERE col = ''``
       (data normalisation, blank string → real NULL)
    2. ``ALTER COLUMN DROP NOT NULL``
       (so the column may carry NULL)

Downgrade: restores "" and NOT NULL in reverse order.

Run after: 0017_requisition_lineage (purchase_orders.requisition_id).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_nullify_no_link_sentinels"
down_revision = "0017_requisition_lineage"
branch_labels = None
depends_on = None

#: (child, column). Exactly the columns that get a FOREIGN KEY in 0019.
SENTINELS: list[tuple[str, str]] = [
    ("categories", "parent_id"),
    ("suppliers", "category_id"),
    ("supplier_certifications", "document_id"),
    ("rfqs", "category_id"),
    ("purchase_orders", "category_id"),
    ("purchase_orders", "requisition_id"),
    ("invoice_lines", "po_line_id"),
    ("invoices", "po_id"),
    ("spend_transactions", "po_id"),
    ("spend_transactions", "invoice_id"),
    ("spend_transactions", "supplier_id"),
    ("catalog_items", "category_id"),
    ("budgets", "category_id"),
    ("documents", "resource_id"),
    ("documents", "resource"),
]


def upgrade() -> None:
    for table, col in SENTINELS:
        op.execute(f"UPDATE {table} SET {col} = NULL WHERE {col} = ''")
        op.alter_column(table, col, existing_type=sa.String(36),
                        existing_nullable=False, nullable=True)


def downgrade() -> None:
    for table, col in SENTINELS:
        op.execute(f"UPDATE {table} SET {col} = '' WHERE {col} IS NULL")
        op.alter_column(table, col, existing_type=sa.String(36),
                        existing_nullable=True, nullable=False)
