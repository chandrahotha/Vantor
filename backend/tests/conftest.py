"""Test fixtures.

- `client` fixture in each module — unchanged. SQLite in memory, no Alembic,
  no RLS. It is deliberately fast and deterministic, and it's what every other
  module uses.
- `pg_client` — the same shape against real Postgres with the schema built
  from alembic. RLS, FKs, composite indexes are all live.

The Postgres half of this file used to be duplicated inside
`test_pg_infrastructure.py` and `test_pg_concurrency.py`, and both copies were
wrong in the same three ways (wrong driver, alembic migrating SQLite, app
engine still on SQLite). It now lives in `pgsupport.py`, once, with the reasons
recorded next to each fix.
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("OIDC_ISSUER", "https://issuer.test/realms/vantor")
os.environ.setdefault("JWT_AUDIENCE", "vantor-web")
os.environ["S3_ENDPOINT"] = ""
os.environ["S3_BUCKET"] = ""

# Sibling-module import that does not depend on pytest's import mode deciding to
# put `tests/` on sys.path before conftest is executed.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pgsupport import (  # noqa: E402  (must follow the env defaults above)
    build_schema,
    pg_app_url,
    pointed_at_postgres,
    purge_tenant,
    require_postgres,
)

PG_TEST_URL = os.getenv("PG_TEST_DATABASE_URL", "").strip()


def _pg_or_skip() -> str:
    return require_postgres()


@pytest.fixture()
def pg_client():
    """Full stack on real Postgres: alembic head, RLS enabled, FKs validated.

    Uses TestClient so every route is reachable, but the schema is built by
    alembic and not create_all, so the RLS policies and the composite FKs are all
    live together.
    """
    url = _pg_or_skip()
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi.testclient import TestClient
    from jwt.algorithms import RSAAlgorithm

    with pointed_at_postgres():
        build_schema()

        # `build_schema()` ran as the owner/migrator role (DDL needs it). The
        # app itself — and so this TestClient — must run as the restricted
        # `vantor_app` role instead, or RLS silently never applies to anything
        # this fixture does, the same gap migration 0026 fixes everywhere else.
        import os

        os.environ["DATABASE_URL"] = pg_app_url()

        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
        jwk["kid"] = "pg-kid"
        from app.core import security
        from app.core.config import get_settings
        from app.core.tenant import reset_engine_cache

        get_settings.cache_clear()
        reset_engine_cache()
        security.override_jwks({"pg-kid": RSAAlgorithm.from_jwk(jwk)})
        from app.main import app as fastapi_app

        tenant = f"pg-{uuid.uuid4().hex[:12]}"
        c = TestClient(fastapi_app, raise_server_exceptions=False)
        yield c, pem, tenant

        # Clean up test rows only — next test sees the same schema.
        purge_tenant(tenant)

        reset_engine_cache()
        get_settings.cache_clear()
        security.override_jwks(None)

    assert url  # the URL was validated before the fixture body ran