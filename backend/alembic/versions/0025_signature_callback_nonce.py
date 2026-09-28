"""Alembic 0025 — a consumed nonce for the e-sign provider callback.

B-19, the remaining window. The inbound HMAC covered `{timestamp}.{body}` with a
fixed tolerance rather than a nonce store, so a signature captured inside
`REPLAY_WINDOW_S` could be replayed: the state transition was idempotent, so a
replay wrote no second row and could not change a terminal status, but every
agreeing replay was still *accepted*, and the acceptance rested on idempotency
rather than on freshness.

`contract_signatures.last_callback_digest` holds the digest of the last accepted
callback. The column is the nonce, stored on the row the callback is scoped to:
one open envelope per provider is already that table's uniqueness constraint, so
the row IS the nonce's scope, and a separate replay table would be a second
lookup for the same fact plus a second operational surface.

A replayed capture matches the stored digest and is refused before the
terminal-state check. A genuinely fresh callback has a new timestamp and
therefore a new digest, so a provider retrying with a fresh signature is not a
replay. Backfilled NULL, which preserves today's behaviour exactly for every
existing row: a row with no digest has simply not received a callback yet.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_signature_callback_nonce"
down_revision = "0024_match_run_price_case_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contract_signatures",
        sa.Column("last_callback_digest", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contract_signatures", "last_callback_digest")
