"""Test fixtures.

- `client` fixture in each module — unchanged. SQLite in memory, no Alembic,
  no RLS. It is deliberately fast and deterministic, and it's what every other
  module uses.
- `pg_client` — the same shape against real Postgres with the schema built
  from alembic. RLS, FKs, composite indexes are all live.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("OIDC_ISSUER", "https://issuer.test/realms/vantor")
os.environ.setdefault("JWT_AUDIENCE", "vantor-web")
os.environ["S3_ENDPOINT"] = ""
os.environ["S3_BUCKET"] = ""

PG_TEST_URL = os.getenv("PG_TEST_DATABASE_URL", "").strip()


def _pg_or_skip() -> str:
    if not PG_TEST_URL:
        pytest.skip("PG_TEST_DATABASE_URL is not set")
    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError

    engine = create_engine(PG_TEST_URL, connect_args={"connect_timeout": 3})
    try:
        engine.connect().close()
    except OperationalError as exc:
        pytest.skip(f"Postgres unreachable at {PG_TEST_URL} ({exc})")
    return PG_TEST_URL


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

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "pg-kid"
    from app.core import security
    from app.core.config import get_settings
    from app.core.tenant import get_engine, reset_engine_cache

    get_settings.cache_clear()
    reset_engine_cache()
    security.override_jwks({"pg-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app
    import uuid

    tenant = f"pg-{uuid.uuid4().hex[:12]}"
    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem, tenant

    # Clean up test rows only — next test sees the same schema.
    from sqlalchemy.orm import Session

    db = Session(get_engine())
    try:
        for table in reversed(db.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'").mappings().scalars()):
            db.execute(f"DELETE FROM {table} WHERE tenant_id = :t", {"t": tenant})
        db.commit()
    finally:
        db.close()

    reset_engine_cache()
    get_settings.cache_clear()
    security.override_jwks(None)