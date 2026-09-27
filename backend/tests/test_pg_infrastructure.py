"""Real Postgres + real schema. Skips cleanly when there is none.

The schema-defect tests assert `alembic check` and FKs. They matter only when
run against the migrations on real Postgres; on SQLite the assertions would be
about SQLAlchemy's behaviour, not about the DDL being what it should be.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

pytestmark = pytest.mark.pg

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


@pytest.fixture()
def pg_client():
    """Full stack on a real Postgres: alembic has run to head, RLS is on."""
    if not os.environ.get("PG_TEST_DATABASE_URL", "").strip():
        pytest.skip("PG_TEST_DATABASE_URL is not set — point it at a Postgres instance")
    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    engine = create_engine(os.environ["PG_TEST_DATABASE_URL"], connect_args={"connect_timeout": 3})
    try:
        engine.connect().close()
    except OperationalError as exc:
        pytest.skip(f"Postgres unreachable at {os.environ['PG_TEST_DATABASE_URL']} ({exc})")

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", os.environ["PG_TEST_DATABASE_URL"])
    command.upgrade(cfg, "head")

    from app.core import security
    from app.core.config import get_settings
    from app.core.tenant import get_engine, reset_engine_cache

    get_settings.cache_clear()
    reset_engine_cache()
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "pg-kid"
    security.override_jwks({"pg-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app
    from fastapi.testclient import TestClient

    tenant = f"pg-{uuid.uuid4().hex[:12]}"
    yield TestClient(fastapi_app, raise_server_exceptions=False), pem, tenant

    db = Session(get_engine())
    try:
        for table in reversed(db.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'").mappings().scalars()):
            db.execute(f"DELETE FROM {table} WHERE tenant_id = :t", {"t": tenant})
        db.commit()
    finally:
        db.close()
    security.override_jwks(None)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="u1", tenant="t1", roles=("Buyer", "Procurement Manager")):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)}, "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "pg-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_database_matches_metadata():
    """`alembic check` — metadata matches DDL, no drift."""
    if not os.environ.get("PG_TEST_DATABASE_URL", "").strip():
        pytest.skip("PG_TEST_DATABASE_URL is not set")
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", os.environ["PG_TEST_DATABASE_URL"])
    command.check(cfg)


def test_every_linked_column_should_have_a_foreign_key():
    """Any `_id` column must have a real `ForeignKey`. The only legitimate
    omissions are the three cross-model polymorphics: `resource_id`
    (documents/approvals) and `envelope_id` (contract signatures, which is an
    external signature-provider reference). everything else is real."""
    from app.models.registry import Base

    assert "documents" in Base.metadata.tables
    assert "approvals" in Base.metadata.tables

    # Polymorphic / cross-entity-only references: there is no single target.
    no_fk = {"documents": {"resource_id"},
             "approvals": {"resource_id"},
             "audit_events": {"resource_id"},
             "contract_signatures": {"envelope_id"}}

    for name, table in sorted(Base.metadata.tables.items()):
        for col in table.columns:
            if col.name.endswith("_id") and col.name != "id" and col.name != "tenant_id":
                if name in no_fk and col.name in no_fk[name]:
                    continue
                assert col.foreign_keys, (
                    f"{name}.{col.name} has no FOREIGN KEY and is not on the "
                    "polymorphic exception list"
                )


def test_invoice_with_cross_po_line_is_rejected(pg_client):
    """In SQLite the bad cross-PO link was silently written. On Postgres the FK says no."""
    c, pem, tenant = pg_client
    h = _h(pem, tenant=tenant)
    sup = c.post("/api/v1/suppliers", json={"code": "S-PG", "name": "PG Supplier"}, headers=h).json()["data"]["id"]
    po1 = c.post("/api/v1/purchase-orders", json={"code": "PO-PG-1", "supplier_id": sup, "currency": "USD",
                                                  "lines": [{"description": "Bolt", "quantity": 1, "unit_price_minor": 10}]},
                 headers=h).json()["data"]["id"]
    po2 = c.post("/api/v1/purchase-orders", json={"code": "PO-PG-2", "supplier_id": sup, "currency": "USD",
                                                  "lines": [{"description": "Nut", "quantity": 1, "unit_price_minor": 10}]},
                 headers=h).json()["data"]["id"]
    l1 = c.get(f"/api/v1/purchase-orders/{po1}", headers=h).json()["data"]["lines"][0]["id"]
    bad = c.post(f"/api/v1/purchase-orders/{po2}/invoices",
                 json={"code": "INV-PG", "lines": [{"po_line_id": l1, "quantity": 1, "unit_price_minor": 10}]},
                 headers=h)
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "INVOICE_LINE_NOT_ON_PO"
