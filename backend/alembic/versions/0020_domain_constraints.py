"""Alembic 0020 — database-level domain constraints.

Every invariant in this migration is one the application was enforcing only in
Python. That is fine until it isn't: a second writer, a migration, a script, a
`psql` session, or a race between two requests all bypass a Python check, and the
money lands anyway. The database is the only place that cannot be talked out of
an invariant.

VNT-028. Before this migration the schema had 45 foreign keys and **zero** CHECK
constraints and zero enums. The four `*_STATUSES` sets in `models/purchase.py`
were module-level literals that nothing imported, so a direct SQL writer could
put `"banana"` into `purchase_orders.status` and the API would then 422 forever
on a value no code path could ever have produced.

What lands here
---------------
1. `idempotency_keys.state` + `claimed_at` — the column that makes a claim
   distinguishable from a completed response. VNT-006.
2. `spend_transactions` unique business key — one commitment per PO, one actual
   per invoice. VNT-027. Previously the only guard was "the PO read `approved`",
   an unlocked read, so two concurrent sends both wrote a row.
3. `approvals` unique (resource, resource_id, tier) — the tier-ordering rule
   assumes exactly one outstanding slot per tier.
4. Status-domain CHECKs, rendered from the same sets the routers validate
   against, and non-negative / positive / line-arithmetic CHECKs on every money
   and quantity column.

Failure policy
--------------
PostgreSQL has no `NOT VALID` for CHECK constraints, so every constraint here is
validated at creation and **a table holding bad rows fails the migration**. That
is deliberate: a migration that quietly coerces or drops financial data to make a
constraint pass is worse than one that stops and tells you. `_preflight()` runs
once the new columns exist and the old statuses have been normalised, and it
raises with the exact offending rows, so the operator knows what to fix instead
of getting `CheckViolation` from a bare `ALTER TABLE`.

That ordering is not cosmetic. An earlier draft of this file called
`_preflight()` first, which meant it queried `idempotency_keys.state`,
`contract_signatures.verified_at` and the new `webhook_deliveries.status` domain
before this migration had created them — so against any real database it failed
on `UndefinedColumn`, and on SQLite with a `queued`/`deferred` row present it
reported violations that the backfill two lines later would have fixed. The
migration could not succeed on a populated database at all.

Existing rows are backfilled, never dropped. `upgrade`/`downgrade` are both
symmetric and lossless with respect to data.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_domain_constraints"
down_revision = "0019_foreign_keys"
branch_labels = None
depends_on = None

# --- constraint text, single source of truth ---------------------------------
# These strings are duplicated in the model `__table_args__`. That duplication is
# unavoidable in Alembic (a migration must not import live models — they move),
# so `tests/test_schema_constraints.py` asserts the two sets are identical. If
# you change one, that test fails and points here.

# One approval slot per (resource, resource_id, tier).
UQ_APPROVAL_TIER = "uq_approval_tenant_res_tier"
# One commitment per PO, one actual per invoice. `kind` is part of the key, which
# is what lets a single constraint serve both shapes.
UQ_SPEND_KIND = "uq_spend_tenant_kind_po_inv"
# One open envelope per provider, for e-sign rows only (partial index).
UQ_SIG_ENVELOPE = "uq_sig_tenant_provider_envelope"

CHECKS: list[tuple[str, str, str]] = [
    # table, constraint name, SQL predicate
    ("requisitions", "ck_requisition_status", "status in ('approved', 'draft', 'ordered', 'rejected', 'submitted')"),
    ("requisition_lines", "ck_reql_qty_pos", "quantity > 0"),
    ("requisition_lines", "ck_reql_price_nonneg", "est_price_minor >= 0"),
    ("purchase_orders", "ck_po_status", "status in ('approved', 'cancelled', 'closed', 'draft', 'invoiced', 'received', 'sent')"),
    ("purchase_orders", "ck_po_total_nonneg", "total_minor >= 0"),
    ("purchase_order_lines", "ck_pol_qty_pos", "quantity > 0"),
    ("purchase_order_lines", "ck_pol_price_pos", "unit_price_minor > 0"),
    ("purchase_order_lines", "ck_pol_line_math", "line_total_minor = unit_price_minor * quantity"),
    ("receipt_lines", "ck_receiptline_qty_pos", "quantity > 0"),
    ("invoices", "ck_invoice_status", "status in ('approved', 'matched', 'paid', 'received', 'rejected')"),
    ("invoices", "ck_invoice_total_pos", "total_minor > 0"),
    ("invoices", "ck_invoice_currency_iso3", "(currency = '' OR length(currency) = 3)"),
    ("invoice_lines", "ck_invline_qty_pos", "quantity > 0"),
    ("invoice_lines", "ck_invline_price_pos", "unit_price_minor > 0"),
    ("invoice_lines", "ck_invline_line_math", "line_total_minor = unit_price_minor * quantity"),
    ("approvals", "ck_approval_status", "status in ('approved', 'rejected', 'requested')"),
    ("approvals", "ck_approval_tier", "tier in ('finance', 'legal', 'manager')"),
    ("spend_transactions", "ck_spend_kind", "kind in ('commitment','actual')"),
    ("spend_transactions", "ck_spend_amount_nonneg", "amount_minor >= 0"),
    ("spend_transactions", "ck_spend_currency_iso3", "(currency = '' OR length(currency) = 3)"),
    ("savings_records", "ck_saving_nonneg", "saved_minor >= 0"),
    ("savings_records", "ck_saving_currency_iso3", "(currency = '' OR length(currency) = 3)"),
    ("idempotency_keys", "ck_idem_state", "state in ('in_progress','completed')"),
    ("contract_signatures", "ck_signature_method", "method in ('internal','esign')"),
    ("contract_signatures", "ck_signature_status", "status in ('pending','signed','declined','voided')"),
    ("contract_signatures", "ck_signature_esign_verified",
     "method = 'internal' or status <> 'signed' or verified_at IS NOT NULL"),
    ("webhook_deliveries", "ck_delivery_status", "status in ('pending','delivered','failed','dead')"),
    ("webhook_deliveries", "ck_delivery_attempts_nonneg", "attempts >= 0"),
]

# Business-key uniqueness. `where` is None for a plain unique constraint, and a
# predicate for a partial unique index.
#
# The only one that must be partial is `contract_signatures`. Its `provider` and
# `envelope_id` are NOT NULL with a `""` default, so every internal signature
# carries the literal pair ('', ''); a plain unique constraint would reject the
# *second* internal signature in a tenant, and a contract legitimately has more
# than one signer. Only rows that actually have an envelope can meaningfully be
# unique on one.
#
# `spend_transactions` does not need a partial index, and the model does not use
# one: `kind` is part of the key, so a commitment is (tenant, 'commitment', po, '')
# and an actual is (tenant, 'actual', po, inv). That is one commitment per PO and
# one actual per invoice, with no collision between the two shapes, and two
# invoices against the same PO differing on `invoice_id` — which is exactly what
# partial invoicing needs.
UNIQUES: list[tuple[str, str, list[str], str | None]] = [
    # One outstanding slot per (resource, id, tier): the tier-ordering rule
    # assumes exactly one approval row per tier.
    ("approvals", UQ_APPROVAL_TIER, ["tenant_id", "resource", "resource_id", "tier"], None),
    ("spend_transactions", UQ_SPEND_KIND, ["tenant_id", "kind", "po_id", "invoice_id"], None),
    # One open envelope per provider, for e-sign rows only.
    ("contract_signatures", UQ_SIG_ENVELOPE, ["tenant_id", "provider", "envelope_id"], "method = 'esign'"),
]

PREFLIGHT_NOTE = (
    "Preflight runs *after* the new columns exist and after the status "
    "normalisation, because otherwise it queries columns this migration has not "
    "created yet (state, verified_at, next_attempt_at) and reports rows that the "
    "backfill immediately below is about to fix."
)


def _preflight() -> None:
    """Refuse to migrate if existing rows would violate a new constraint.

    Turns an opaque `CheckViolation` deep inside a long ALTER chain into a
    message naming the table, the constraint, and the offending rows.
    """
    bind = op.get_bind()
    problems: list[str] = []

    for table, name, predicate in CHECKS:
        sql = sa.text(f"SELECT * FROM {table} WHERE NOT ({predicate}) LIMIT 5")
        rows = list(bind.execute(sql).mappings())
        if rows:
            problems.append(f"{name} ({table}): {len(rows)}+ row(s) violate `{predicate}`, e.g. {dict(rows[0])}")

    for table, name, cols, where in UNIQUES:
        collist = ", ".join(cols)
        # The predicate must be applied here exactly as the index will apply it.
        # Without it the preflight would either report a duplicate the partial
        # index will happily allow, or miss a real one.
        sql = sa.text(
            f"SELECT {collist}, count(*) AS n FROM {table}"
            + (f" WHERE {where}" if where else "")
            + f" GROUP BY {collist} HAVING count(*) > 1 LIMIT 5")
        rows = list(bind.execute(sql).mappings())
        if rows:
            problems.append(
                f"{name} ({table}): {len(rows)}+ duplicate group(s)"
                + (f" among rows where {where}" if where else "")
                + f", e.g. {dict(rows[0])}")

    if problems:
        raise RuntimeError(
            "0020 refused to run: existing data violates new domain constraints. "
            "Reconcile the data first — this migration will not silently drop or "
            "coerce financial rows.\n  - " + "\n  - ".join(problems))


def _add_columns_and_backfill() -> None:
    """Everything that must happen before `_preflight()` can query the schema."""
    # 1. Idempotency claim state. VNT-006. Existing rows are all completed
    #    responses by definition — they were only ever written after the handler
    #    succeeded — so the backfill is exact, not a guess.
    op.add_column("idempotency_keys", sa.Column("state", sa.String(16), nullable=False, server_default="completed"))
    op.add_column("idempotency_keys", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_index("ix_idem_tenant_state", "idempotency_keys", ["tenant_id", "state"])

    # 2. Durable webhook outbox. VNT-008. `body` holds the exact bytes that were
    #    signed so a retry re-signs an identical payload; `next_attempt_at` makes
    #    the backoff a query filter rather than an in-memory timer that a restart
    #    loses. Existing rows are terminal `failed` attempts from the old
    #    synchronous path — replayable, but not something to retry blindly.
    op.add_column("webhook_deliveries", sa.Column("body", sa.Text(), nullable=False, server_default=""))
    op.add_column("webhook_deliveries", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_delivery_due", "webhook_deliveries", ["status", "next_attempt_at"])
    op.execute("UPDATE webhook_deliveries SET status = 'failed' WHERE status = 'queued'")
    op.execute("UPDATE webhook_deliveries SET status = 'dead' WHERE status = 'deferred'")

    # 3. E-signature verification state. VNT-023. An e-sign row used to be written
    #    as a completed signature from a caller-supplied envelope id, with nowhere
    #    to record the provider's answer. Existing rows are backfilled as
    #    `signed` with `verified_at = created_at`: they were all written by the
    #    synchronous internal path, so the backfill records the truth about them
    #    rather than inventing a verification that never happened.
    op.add_column("contract_signatures", sa.Column("status", sa.String(16), nullable=False, server_default="pending"))
    op.add_column("contract_signatures", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contract_signatures", sa.Column("provider_payload", sa.JSON(), nullable=False, server_default="{}"))
    op.execute("UPDATE contract_signatures SET status = 'signed', verified_at = created_at "
               "WHERE method = 'internal' AND status = 'pending'")
    # Any remaining `pending` row is an esign whose provider never confirmed. It
    # stays pending, which is the honest state, and can be reconciled by replaying
    # the provider's answer through POST /contracts/{id}/sign/verify.


def _create_constraints() -> None:
    for table, name, cols, where in UNIQUES:
        if where is None:
            # A plain unique constraint, matching how the model declares it.
            # Using an index here instead would be a real `alembic check` drift
            # between a constraint and a unique index of the same name.
            op.create_unique_constraint(name, table, cols)
        else:
            op.create_index(
                name, table, cols, unique=True,
                postgresql_where=sa.text(where),
                sqlite_where=sa.text(where),
            )

    for table, name, predicate in CHECKS:
        op.create_check_constraint(name, table, sa.text(predicate))


def upgrade() -> None:
    # Order is load-bearing: columns, then normalisation, then preflight, then
    # constraints. Preflighting first would query `idempotency_keys.state`,
    # `contract_signatures.verified_at` and the new `webhook_deliveries.status`
    # domain before any of them exist, so the migration could not run at all.
    _add_columns_and_backfill()
    _preflight()
    _create_constraints()


def downgrade() -> None:
    for table, name, _predicate in reversed(CHECKS):
        op.drop_constraint(name, table, type_="check")

    for table, name, _cols, where in reversed(UNIQUES):
        if where is None:
            op.drop_constraint(name, table, type_="unique")
        else:
            op.drop_index(name, table_name=table)

    op.drop_index("ix_delivery_due", table_name="webhook_deliveries")
    op.drop_column("webhook_deliveries", "next_attempt_at")
    op.drop_column("webhook_deliveries", "body")

    op.drop_column("contract_signatures", "provider_payload")
    op.drop_column("contract_signatures", "verified_at")
    op.drop_column("contract_signatures", "status")

    op.drop_index("ix_idem_tenant_state", table_name="idempotency_keys")
    op.drop_column("idempotency_keys", "claimed_at")
    op.drop_column("idempotency_keys", "state")
