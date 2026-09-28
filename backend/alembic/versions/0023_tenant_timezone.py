"""Alembic 0023 — a business timezone per tenant.

VNT-024, second residue. "Within 90 days" is a judgement made in the buyer's
working day, and it was evaluated against one deployment-wide
`CONTRACT_TIMEZONE`. For any tenant that is not at the operator's longitude that
is wrong: a buyer at UTC-12 reaches their own 1 January twelve hours before a UTC
server does, so the renewal notice fires a day early or a day late, and the
expiry window is quietly twelve hours out for them.

The tenants of a procurement system are normally in different countries, so
per-tenant is the only correct granularity - a deployment-wide zone is a setting
that happens to be right for exactly one customer.

`organizations.timezone` holds an IANA zone name, empty meaning "inherit the
deployment setting". Backfilled as empty, which preserves today's behaviour
exactly for every existing row; a tenant that wants its own zone sets it, and
`contracts._tenant_today` prefers it.

An unknown or malformed zone falls back to the deployment setting and then to UTC.
A bad row must not stop the nightly roll for that tenant - a stale contract status
is recoverable, a queue that stops draining is not.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_tenant_timezone"
down_revision = "0022_pgvector_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("timezone", sa.String(64), nullable=False, server_default=""),
    )
    # Empty means "inherit", which is exactly what every existing tenant had, so
    # the deployment setting keeps applying and nothing changes on upgrade. The
    # server default is then dropped so a row inserted without the column is an
    # error rather than a silent inheritance.
    op.alter_column("organizations", "timezone", server_default=None)


def downgrade() -> None:
    op.drop_column("organizations", "timezone")
