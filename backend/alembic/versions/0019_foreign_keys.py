"""Alembic — real, audited foreign keys across the whole schema.

Every link the application was validating in Python is now enforced by the
database too. The links are:

  categories.parent_id            → categories.id
  suppliers.category_id           → categories.id
  supplier_contacts.supplier_id   → suppliers.id
  supplier_certifications.*       → suppliers.id / documents.id
  supplier_qualifications.*       → suppliers.id
  supplier_scorecards.*           → suppliers.id
  rfqs.category_id                → categories.id
  rfq_lines.rfq_id                → rfqs.id
  quotes.rfq_id / supplier_id     → rfqs.id / suppliers.id
  quote_lines.quote_id / rfq_line_id → quotes.id / rfq_lines.id
  awards.*                        → rfqs.id / quotes.id
  contracts.supplier_id           → suppliers.id
  contract_obligations.*          → contracts.id
  contract_signatures.*           → contracts.id
  requisition_lines.*             → requisitions.id
  purchase_orders.…               → suppliers.id / categories.id / requisitions.id
  purchase_order_lines.…          → purchase_orders.id
  receipts.…                      → purchase_orders.id
  receipt_lines.…                 → receipts.id / purchase_order_lines.id
  invoices.…                      → purchase_orders.id / suppliers.id
  invoice_lines.…                 → invoices.id / purchase_order_lines.id
  spend_transactions.…            → purchase_orders.id / invoices.id / suppliers.id
  savings_records.…               → rfqs.id / awards.id
  catalog_items.category_id       → categories.id
  documents.…                     → (none — resource_id is polymorphic)
  document_chunks.…               → documents.id
  webhook_deliveries.endpoint_id  → webhook_endpoints.id

Method: each parent gets a composite unique index on (tenant_id, id), and the
FK references those two columns. Since every table carries a `tenant_id` and a
primary key on `id`, the composite reference guarantees tenant equality as well
as row existence, even if RLS were ever bypassed.

Maange the child lock down with RESTRICT: a parent with a child is never deleted;
deletes are expressed by unlinking the child (setting NULL).

Each FK is added NOT VALID first (no scan of existing rows), then VALIDATE in the
same transaction. Dirty data cannot roll it back — migration fails loudly with
no schema applied.
"""
from __future__ import annotations

from alembic import op

revision = "0019_foreign_keys"
down_revision = "0018_nullify_no_link_sentinels"
branch_labels = None
depends_on = None

#: (child_table, child_col, parent_table). One composite index per parent,
#: shared by all links that reference it.
FKS: list[tuple[str, str, str]] = [
    ("categories", "parent_id",      "categories"),
    ("suppliers", "category_id",     "categories"),
    ("supplier_contacts", "supplier_id", "suppliers"),
    ("supplier_certifications", "supplier_id", "suppliers"),
    ("supplier_certifications", "document_id", "documents"),
    ("supplier_qualifications", "supplier_id", "suppliers"),
    ("supplier_scorecards", "supplier_id", "suppliers"),
    ("rfqs", "category_id",          "categories"),
    ("rfq_lines", "rfq_id",          "rfqs"),
    ("quotes", "rfq_id",             "rfqs"),
    ("quotes", "supplier_id",        "suppliers"),
    ("quote_lines", "quote_id",      "quotes"),
    ("quote_lines", "rfq_line_id",   "rfq_lines"),
    ("awards", "rfq_id",             "rfqs"),
    ("awards", "quote_id",           "quotes"),
    ("contracts", "supplier_id",     "suppliers"),
    ("contract_obligations", "contract_id", "contracts"),
    ("contract_signatures", "contract_id", "contracts"),
    ("requisition_lines", "requisition_id", "requisitions"),
    ("purchase_orders", "supplier_id",     "suppliers"),
    ("purchase_orders", "category_id",     "categories"),
    ("purchase_orders", "requisition_id",  "requisitions"),
    ("purchase_order_lines", "po_id",       "purchase_orders"),
    ("receipts", "po_id",                   "purchase_orders"),
    ("receipt_lines", "receipt_id",          "receipts"),
    ("receipt_lines", "po_line_id",         "purchase_order_lines"),
    ("invoices", "po_id",                  "purchase_orders"),
    ("invoices", "supplier_id",            "suppliers"),
    ("invoice_lines", "invoice_id",        "invoices"),
    ("invoice_lines", "po_line_id",        "purchase_order_lines"),
    ("spend_transactions", "po_id",         "purchase_orders"),
    ("spend_transactions", "invoice_id",    "invoices"),
    ("spend_transactions", "supplier_id",    "suppliers"),
    ("savings_records", "rfq_id",           "rfqs"),
    ("savings_records", "award_id",         "awards"),
    ("catalog_items", "category_id",        "categories"),
    ("budgets", "category_id",              "categories"),
    ("document_chunks", "document_id",       "documents"),
    ("webhook_deliveries", "endpoint_id",    "webhook_endpoints"),
]
PARENTS = sorted({p for _, _, p in FKS})


def _fk(child: str, col: str) -> str:
    return f"fk_{child}_{col}"


def _uq_idx(parent: str) -> str:
    return f"uq_{parent}_tenant_id_id"


def upgrade() -> None:
    # 1. One composite unique index per parent so the FK can reference both
    #    tenant_id and the primary key.
    for parent in PARENTS:
        op.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS {_uq_idx(parent)} '
            f'ON {parent} (tenant_id, id)'
        )
    # 2. Every FK is created NOT VALID first (no row scan on existing data),
    #    then VALIDATE in the same transaction. Dirty data rolls it all back —
    #    no dirty row can evade the constraint.
    for child, col, parent in FKS:
        cname = _fk(child, col)
        op.execute(
            f'ALTER TABLE {child} ADD CONSTRAINT {cname} '
            f'FOREIGN KEY (tenant_id, {col}) '
            f'REFERENCES {parent} (tenant_id, id) '
            f'ON DELETE RESTRICT ON UPDATE RESTRICT NOT VALID'
        )
    for child, col, _ in FKS:
        op.execute(f"ALTER TABLE {child} VALIDATE CONSTRAINT {_fk(child, col)}")


def downgrade() -> None:
    for child, col, _ in reversed(FKS):
        op.execute(f"ALTER TABLE {child} DROP CONSTRAINT IF EXISTS {_fk(child, col)}")
    for parent in PARENTS:
        op.execute(f"DROP INDEX IF EXISTS {_uq_idx(parent)}")
