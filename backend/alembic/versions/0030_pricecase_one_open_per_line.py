"""Alembic 0030 — one open price case per PO line, enforced by the database.

`POST /spend/price-cases` evaluates every line of a purchase order in one pass:
it reads the set of lines that already have an open case, then inserts a case for
each line that does not. Between the read and the insert there is no lock and,
until now, no constraint — so two concurrent evaluations on the same PO both saw
"no open case for line 3" and both opened one. The result is not a crash: it is
two open anomaly cases for one line, which is a claim about the same money
counted twice, and it is what a reviewer then has to reconcile by hand.

The endpoint's read-then-write shape is inherent (it is a batch evaluation), so
the interlock cannot live in the handler. It goes in the database, where the
arbitration is atomic.

The duplicate rows this bug already created are repaired first, into a status the
application's own state machine recognises (`open → handed_off | dismissed`,
`routers/spend.py:294`) rather than an invented one, and `updated_by` records
which migration did it. Nothing is deleted: every row stays queryable, and the
case that survives is the earliest one, because that is the one a reviewer would
already have been looking at.

`po_line_id <> ''` appears in both the repair and the index predicate. Cases
raised without a specific line default that column to the empty string, and
without the clause the first such case in a tenant would block every later one —
a constraint that silently refuses legitimate work is worse than no constraint.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_pricecase_one_open_per_line"
down_revision = "0029_esign_tenant_resolver"
branch_labels = None
depends_on = None

INDEX = "uq_pricecase_one_open_per_line"
PREDICATE = "status = 'open' AND po_line_id <> ''"


def _duplicate_open_case_ids(bind) -> list[str]:
    """Ids of all but the earliest open case for each (tenant, line)."""
    rows = list(bind.execute(sa.text(
        """
        SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY tenant_id, po_line_id
                       ORDER BY created_at, id
                   ) AS rn
            FROM price_cases
            WHERE status = 'open' AND po_line_id <> ''
        ) ranked
        WHERE rn > 1
        """
    )).scalars())
    return [str(r) for r in rows]


def retire_statement(count: int) -> str:
    """The UPDATE that retires duplicates, built in one place.

    A generated bind-parameter list is the kind of string that only fails when it
    runs, and a test that re-spells the statement tests its own copy rather than
    this one. So the statement is assembled here and the test calls this.
    """
    return (
        "UPDATE price_cases "
        "SET status = 'dismissed', updated_by = :who "
        "WHERE id IN (" + ",".join(f":i{i}" for i in range(count)) + ")"
    )


def upgrade() -> None:
    bind = op.get_bind()

    stale = _duplicate_open_case_ids(bind)
    if stale:
        # Batched so a pathological table cannot build one enormous IN list. The
        # keyset is stable for the duration because this is the only writer that
        # touches these rows during the migration.
        batch = 500
        for start in range(0, len(stale), batch):
            chunk = stale[start:start + batch]
            bind.execute(
                sa.text(retire_statement(len(chunk))),
                {"who": "migration:0030_dedupe", **{f"i{i}": cid for i, cid in enumerate(chunk)}},
            )
        print(
            f"0030: retired {len(stale)} duplicate open price case(s) to "
            f"`dismissed` (updated_by='migration:0030_dedupe') so the unique index "
            "could be created. The earliest case per line was kept open."
        )

    op.create_index(
        INDEX,
        "price_cases",
        ["tenant_id", "po_line_id"],
        unique=True,
        postgresql_where=sa.text(PREDICATE),
        sqlite_where=sa.text(PREDICATE),
    )


def downgrade() -> None:
    # The index only. The rows retired during upgrade are not re-opened: which
    # duplicate a reviewer meant to keep is not recoverable from the data, and
    # silently re-opening N cases would resurrect the double-counted claims the
    # upgrade resolved.
    op.drop_index(INDEX, table_name="price_cases")
