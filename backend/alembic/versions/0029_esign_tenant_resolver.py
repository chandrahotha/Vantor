"""Alembic 0029 — the e-sign provider callback can see its envelope under RLS.

The provider-callback route (`POST /contracts/signatures/provider-callback`) is
the only endpoint in the product that takes its DB session without a tenant
pin: the caller is the provider, not a VANTOR user, so there is no verified JWT
to take a tenant from. On PostgreSQL as `vantor_app` (migration 0026,
`NOBYPASSRLS`) row-level security therefore applied to the lookup with
`app.tenant_id` unset — and every `tenant_isolation` policy compares
`tenant_id = current_setting('app.tenant_id', true)`, which with no setting
evaluates to NULL and matches no row. Every correctly-signed callback was
refused `422 ESIGN_ENVELOPE_NOT_FOUND` for an envelope that existed, on the
deployment posture 0026 itself mandates. It worked on SQLite (no RLS), so the
suite stayed green — the tested-on-the-mock shape this chain has recorded
before.

The lookup is cross-tenant by design — the envelope is the provider's, and
which tenant it belongs to is exactly what the callback has to discover — so
this migration adds a `SECURITY DEFINER` function that performs that one
lookup with the table owner's rights and nothing more. It returns the match
count and the tenant; the application refuses 0 matches and more than one, and
pins the resolved tenant before re-running the locked, RLS-satisfied lookup.

The function reads one table and grants nothing: revoking PUBLIC's default
EXECUTE and granting it to `vantor_app` keeps the callable surface to the
application role.

Revision ID: 0029_esign_tenant_resolver
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0029_esign_tenant_resolver"
down_revision = "0028_spend_commitment_unique"
branch_labels = None
depends_on = None

FUNCTION_SQL = (
    "CREATE OR REPLACE FUNCTION app_esign_envelope_tenant(p_provider text, p_envelope text) "
    "RETURNS TABLE (match_count bigint, tenant_id text) "
    "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$ "
    "SELECT count(*) AS match_count, min(tenant_id) AS tenant_id "
    "FROM contract_signatures "
    "WHERE provider = p_provider AND envelope_id = p_envelope "
    "$$"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite has no RLS and no server-side functions; the callback's lookup
        # already sees every row there, so the resolver has nothing to do.
        return
    op.execute(sa.text(FUNCTION_SQL))
    # Functions default to EXECUTE granted to PUBLIC; the function is a
    # SECURITY DEFINER read across tenants, so the callable surface is the
    # application role and nothing else. Guarded, because 0026 (which creates
    # the role) runs before this revision but the role may have been dropped
    # out-of-band on a database this migration is replayed against.
    op.execute(
        sa.text(
            "REVOKE ALL ON FUNCTION app_esign_envelope_tenant(text, text) FROM PUBLIC"
        )
    )
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'vantor_app') THEN "
            "GRANT EXECUTE ON FUNCTION app_esign_envelope_tenant(text, text) TO vantor_app; "
            "END IF; END $$;"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text("DROP FUNCTION IF EXISTS app_esign_envelope_tenant(text, text)"))
