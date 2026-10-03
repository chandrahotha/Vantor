"""Alembic 0027 — the three status enums 0020 missed.

0020_domain_constraints.py added DB-level CHECK constraints for every status
enum enforced by a router *except* `contracts.status`, `contract_obligations.status`,
and `documents.status` — the same unenforced-literal pattern VNT-028 described,
for three tables the first pass missed (RA-008, re-audit 2026-10-02). Mirrors
0020's own pattern exactly: preflight against existing data first, so this
refuses loudly on a row that would violate the constraint rather than silently
dropping or coercing it.

Revision ID: 0027_remaining_status_checks
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0027_remaining_status_checks"
down_revision = "0026_app_role_least_privilege"
branch_labels = None
depends_on = None

# table, constraint name, predicate — values taken directly from
# app/models/contract.py (CONTRACT_STATUSES, OBLIGATION_STATUSES) and
# app/models/document.py (DOC_STATUSES), sorted to match the `_in()` helper
# those models use to render their own CheckConstraint — alembic check and
# tests/test_schema_constraints.py both compare predicate text, not semantics.
CHECKS: list[tuple[str, str, str]] = [
    ("contracts", "ck_contract_status",
     "status in ('active', 'draft', 'expired', 'expiring', 'renewed', 'review', 'terminated')"),
    ("contract_obligations", "ck_obligation_status",
     "status in ('done', 'open', 'overdue', 'waived')"),
    ("documents", "ck_document_status",
     "status in ('quarantined', 'ready', 'uploaded')"),
]


def _preflight() -> None:
    bind = op.get_bind()
    problems: list[str] = []
    for table, name, predicate in CHECKS:
        rows = list(bind.execute(sa.text(f"SELECT * FROM {table} WHERE NOT ({predicate}) LIMIT 5")).mappings())
        if rows:
            problems.append(f"{name} ({table}): {len(rows)}+ row(s) violate `{predicate}`, e.g. {dict(rows[0])}")
    if problems:
        raise RuntimeError(
            "0027 refused to run: existing data violates a new status constraint. "
            "Reconcile the data first — this migration will not silently drop or "
            "coerce rows.\n  - " + "\n  - ".join(problems))


def upgrade() -> None:
    _preflight()
    for table, name, predicate in CHECKS:
        op.create_check_constraint(name, table, sa.text(predicate))


def downgrade() -> None:
    for table, name, _predicate in reversed(CHECKS):
        op.drop_constraint(name, table, type_="check")
