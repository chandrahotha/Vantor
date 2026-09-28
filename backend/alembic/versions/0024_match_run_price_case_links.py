"""Alembic — constrain the last six links in the schema.

`0019_foreign_keys` covered 40 links. It missed the two tables added after it:
`match_runs` and `price_cases`. Their models declared single-column
`ForeignKey("purchase_orders.id")` and friends, but the database never had the
constraint, so:

* the ORM believed a link was enforced when it was not, and
* `test_database_matches_metadata` had been reporting them as
  `remove foreign key` — phantom differences that made the test unusable for
  spotting the drift that mattered.

An unconstrained `po_id` on a price case is the same leak the other forty
constraints exist to close: a row can name a purchase order that belongs to a
different tenant, and every read scoped by `tenant_id` then returns a record
whose subject is invisible. This adds the same composite
`(tenant_id, <col>) -> <parent>(tenant_id, id)` reference used everywhere else.

These six columns are required, not optional, so no `""`-to-NULL conversion is
involved — they keep `NOT NULL`, and a row that must reference something is
better served by the database refusing a dangling id than by the application
remembering to check.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_match_run_price_case_links"
down_revision = "0023_tenant_timezone"
branch_labels = None
depends_on = None

#: (child, column, parent). The last six links, matching
#: `app/models/{matchrun,pricecase}.py`.
FKS: list[tuple[str, str, str]] = [
    ("match_runs", "contract_id", "contracts"),
    ("match_runs", "po_id", "purchase_orders"),
    ("match_runs", "invoice_id", "invoices"),
    ("price_cases", "po_id", "purchase_orders"),
    ("price_cases", "po_line_id", "purchase_order_lines"),
    ("price_cases", "supplier_id", "suppliers"),
]

PARENTS = sorted({p for _, _, p in FKS})


def upgrade() -> None:
    for parent in PARENTS:
        op.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS uq_{parent}_tenant_id_id '
            f'ON {parent} (tenant_id, id)'
        )

    # `.mappings()` rather than bare iteration, matching `_preflight()` in 0020:
    # it is the same read against `pg_constraint` and the same result handling.
    existing = {
        str(row["conname"])
        for row in op.get_bind().execute(
            sa.text("SELECT conname FROM pg_constraint WHERE contype = 'f'")
        ).mappings()
    }
    for child, col, parent in FKS:
        cname = f"fk_{child}_{col}"
        if cname in existing:
            continue
        # NOT VALID first so adding the constraint does not scan the table, then
        # VALIDATE in the same transaction: a row that already points at another
        # tenant fails the migration loudly instead of surviving it.
        op.execute(
            f'ALTER TABLE {child} ADD CONSTRAINT {cname} '
            f'FOREIGN KEY (tenant_id, {col}) '
            f'REFERENCES {parent} (tenant_id, id) '
            f'ON DELETE RESTRICT ON UPDATE RESTRICT NOT VALID'
        )
        op.execute(f"ALTER TABLE {child} VALIDATE CONSTRAINT {cname}")


def downgrade() -> None:
    for child, col, _ in reversed(FKS):
        op.execute(f"ALTER TABLE {child} DROP CONSTRAINT IF EXISTS fk_{child}_{col}")
