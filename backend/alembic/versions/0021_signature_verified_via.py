"""Alembic 0021 — record *how* a signature was verified.

VNT-023, second half. 0020 added `contract_signatures.status` and `verified_at`,
so the schema could say a signature was confirmed and when. It still could not
say **on whose word**, which is the question a contract dispute actually asks:

* the e-sign provider answered, over a callback whose HMAC we verified; or
* a legal reviewer typed the outcome into an authenticated form.

Those are very different claims and `verified_at` renders them identically. An
operator could mark any envelope `signed`, and the row — hash-chained, audited,
and constrained by `ck_signature_esign_verified` — would be indistinguishable
from one the provider confirmed. The audit trail said a signature existed without
saying who vouched for it.

`verified_via` closes that. It is a small column and it is the difference between
"the system knows this was signed" and "the system knows *this* is what signed it".

Backfill
--------
Existing rows are labelled from what is known, not guessed:

* `method = 'internal'` -> `internal_click`. Those rows are an authenticated
  click by definition; they never had a provider in the loop.
* `method = 'esign'` and already `signed` -> `manual_reconciliation`. Every one of
  them reached `signed` through the operator-facing endpoint, because until this
  migration there was no other way. Labelling them `provider_callback` would be
  inventing a verification that demonstrably did not happen.
* anything still `pending` -> `""`, meaning unverified, which is the truth.

The new CHECKs are added only after the backfill, so the migration cannot fail on
rows this column is meant to classify.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_signature_verified_via"
down_revision = "0020_domain_constraints"
branch_labels = None
depends_on = None

VERIFIED_VIA_CHECKS: list[tuple[str, str, str]] = [
    (
        "contract_signatures",
        "ck_signature_verified_via",
        "verified_via in ('','provider_callback','manual_reconciliation','internal_click')",
    ),
    (
        "contract_signatures",
        "ck_signature_esign_verified_via",
        "method = 'internal' or status <> 'signed' or verified_via <> ''",
    ),
]


def upgrade() -> None:
    op.add_column(
        "contract_signatures",
        sa.Column("verified_via", sa.String(24), nullable=False, server_default=""),
    )
    # Internal signatures are an authenticated click and never had a provider.
    op.execute("UPDATE contract_signatures SET verified_via = 'internal_click' "
               "WHERE method = 'internal'")
    # Every esign row already `signed` got there through the operator endpoint.
    op.execute("UPDATE contract_signatures SET verified_via = 'manual_reconciliation' "
               "WHERE method = 'esign' AND status = 'signed'")
    # Drop the server default: it exists only so the ADD COLUMN above can be
    # NOT NULL on a populated table, and leaving it would silently write '' for
    # any future row that forgot the column.
    op.alter_column("contract_signatures", "verified_via", server_default=None)

    for table, name, predicate in VERIFIED_VIA_CHECKS:
        op.create_check_constraint(name, table, sa.text(predicate))


def downgrade() -> None:
    for table, name, _predicate in reversed(VERIFIED_VIA_CHECKS):
        op.drop_constraint(name, table, type_="check")
    op.drop_column("contract_signatures", "verified_via")
