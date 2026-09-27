"""Add the requisition lineage column to purchase_orders.

Column only here. The actual FOREIGN KEY constraint arrives in 0019, with the
rest of the schema-wide FK work, so the migrations follow the dependency order
they enforce.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_requisition_lineage"
down_revision = "0016_idempotency_key_width"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchase_orders", sa.Column("requisition_id", sa.String(36), nullable=True))
    op.create_index("ix_po_tenant_req", "purchase_orders", ["tenant_id", "requisition_id"])


def downgrade() -> None:
    op.drop_index("ix_po_tenant_req", table_name="purchase_orders")
    op.drop_column("purchase_orders", "requisition_id")
