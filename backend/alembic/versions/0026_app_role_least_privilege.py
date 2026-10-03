"""Alembic 0026 — a restricted role for the application connection.

Every tenant table since 0001 has carried `ENABLE ROW LEVEL SECURITY` plus a
`tenant_isolation` policy, on the assumption that this is a real backstop if
an application-level `tenant_id` filter is ever forgotten. It was not: every
deployment path (docker-compose.yml, the single-container image, local dev,
and CI) points `DATABASE_URL` at `POSTGRES_USER`, which is the role the
official postgres Docker image creates at `initdb` time with `SUPERUSER`.
Postgres never applies row security to a superuser or to a role with
`BYPASSRLS`, regardless of `FORCE ROW LEVEL SECURITY` — so every
`tenant_isolation` policy in this schema has been a no-op for the
application's own connection since 0001. Proven live, not inferred: as the
`vantor` role, `SELECT * FROM <any tenant table>` returns every tenant's rows
even with `app.tenant_id` correctly pinned via `set_config`.

This migration creates a second role, `vantor_app`, that is a plain member of
no privileged group (`NOSUPERUSER NOBYPASSRLS`, and critically not the table
owner), grants it exactly the privileges the application needs, and nothing
more:

- `audit_events`: SELECT, INSERT, UPDATE, but no DELETE. UPDATE cannot be
  dropped the way the original "applied by ops, not here" GRANT comment in
  0001 intended: `services/audit.py` takes `SELECT ... FOR UPDATE` on the
  tenant's chain tail to serialise concurrent writers, and Postgres requires
  UPDATE privilege on the table to take that lock at all — confirmed by
  reproducing `InsufficientPrivilege` against a SELECT-only grant. DELETE is
  still blocked, and the application code never issues an UPDATE against an
  existing row (only INSERT), so this is weaker than full immutability but a
  real improvement over no grant restriction at all.
- every other tenant table: SELECT, INSERT, UPDATE, DELETE.
- `ALTER DEFAULT PRIVILEGES` for the migrator role so a future migration's new
  table is covered automatically and this does not silently regress the next
  time someone adds a table.

`DATABASE_URL` for the running application (backend, worker, beat, and the
Postgres-backed test tier) must point at `vantor_app`, not at `POSTGRES_USER`.
Migrations keep running as the owner/superuser role — `vantor_app` owns
nothing and cannot run DDL.

Revision ID: 0026_app_role_least_privilege
"""
from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa

revision = "0026_app_role_least_privilege"
down_revision = "0025_signature_callback_nonce"
branch_labels = None
depends_on = None

APP_ROLE = "vantor_app"
NO_DELETE = {"audit_events"}


def _app_db_password() -> str:
    pw = os.environ.get("APP_DB_PASSWORD", "").strip()
    if not pw or pw in ("change-me-in-env", "generate-32-bytes-min"):
        raise RuntimeError(
            "APP_DB_PASSWORD is missing or a placeholder. Migration 0026 creates "
            "the least-privilege application role and must set a real password "
            "for it — set APP_DB_PASSWORD in the environment running this "
            "migration (., CI, or docker-compose) before upgrading."
        )
    return pw


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite has no roles and no RLS; this migration is a Postgres-only
        # security control and is a no-op everywhere else, same as the RLS
        # statements in every earlier migration.
        return

    password = _app_db_password()

    op.execute(
        sa.text(
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN "
            f"CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS; "
            f"END IF; END $$;"
        )
    )
    # ALTER ROLE ... PASSWORD takes no bind parameter; building the statement
    # via `format(..., %L)` with a bound value keeps the password out of the
    # migration source while still escaping it safely against SQL injection
    # (a literal quote in the password cannot break out of the string).
    conn = op.get_bind()
    alter_sql = conn.execute(
        sa.text(f"SELECT format('ALTER ROLE {APP_ROLE} WITH PASSWORD %L', CAST(:pw AS text))"), {"pw": password}
    ).scalar_one()
    conn.execute(sa.text(alter_sql))

    op.execute(f"GRANT CONNECT ON DATABASE {conn.engine.url.database} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")

    inspector = sa.inspect(bind)
    for table in inspector.get_table_names(schema="public"):
        if table in ("alembic_version",):
            continue
        if table in NO_DELETE:
            op.execute(f"GRANT SELECT, INSERT, UPDATE ON public.{table} TO {APP_ROLE}")
        else:
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO {APP_ROLE}")

    # Covers tables created by later migrations (run as the owner) without
    # needing this file edited again.
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {conn.engine.url.username} IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    conn = op.get_bind()
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {conn.engine.url.username} IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}"
    )
    inspector = sa.inspect(bind)
    for table in inspector.get_table_names(schema="public"):
        op.execute(f"REVOKE ALL ON public.{table} FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE CONNECT ON DATABASE {conn.engine.url.database} FROM {APP_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
