"""Supplier Wave 2.1 tests - CRUD, data-grid pagination, tenant isolation, audit.

Runs on sqlite (no external PG/Keycloak). API tests use real RS256 JWTs.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


@pytest.fixture()
def app_client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("JWT_AUDIENCE", AUD)
    from app.core.config import get_settings
    from app.core.tenant import get_engine, reset_engine_cache

    get_settings.cache_clear()
    reset_engine_cache()
    engine = get_engine()
    from app.models.registry import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "t-kid"
    from app.core import security

    security.override_jwks({"t-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    client = TestClient(fastapi_app, raise_server_exceptions=False)
    yield client, priv_pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _tok(priv_pem: bytes, tenant="t1", roles=("Buyer",)):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"iss": ISS, "aud": AUD, "sub": "u1", "tenant_id": tenant,
         "realm_access": {"roles": list(roles)}, "exp": now + timedelta(minutes=5), "iat": now},
        priv_pem, algorithm="RS256", headers={"kid": "t-kid"},
    )


def _auth(priv_pem: bytes, tenant="t1", roles=("Buyer",)):
    return {"Authorization": f"Bearer {_tok(priv_pem, tenant, roles)}"}


def test_create_list_paginate_and_audit(app_client):
    client, priv = app_client
    h = _auth(priv, "acme")
    for i in range(3):
        r = client.post("/api/v1/suppliers", json={"code": f"SUP-{i:03d}", "name": f"Supplier {i}", "country": "IN", "currency": "INR"}, headers=h)
        assert r.status_code == 201, r.text
    r = client.get("/api/v1/suppliers?limit=2", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["hasMore"] is True
    cur = body["pagination"]["nextCursor"]
    r2 = client.get(f"/api/v1/suppliers?limit=2&cursor={cur}", headers=h)
    assert len(r2.json()["data"]) == 1
    # audit trail written server-side
    r3 = client.get("/api/v1/audit-events?action=SUPPLIER_CREATED", headers=h)
    assert r3.status_code == 200
    assert len(r3.json()["data"]) == 3


def test_cross_tenant_invisible(app_client):
    client, priv = app_client
    r = client.post("/api/v1/suppliers", json={"code": "SUP-X", "name": "X Corp"}, headers=_auth(priv, "tenant-a"))
    sid = r.json()["data"]["id"]
    assert client.get(f"/api/v1/suppliers/{sid}", headers=_auth(priv, "tenant-b")).status_code == 404
    assert client.get("/api/v1/suppliers", headers=_auth(priv, "tenant-b")).json()["data"] == []


def test_validation_and_lifecycle(app_client):
    client, priv = app_client
    h = _auth(priv, "t9")
    assert client.post("/api/v1/suppliers", json={"code": "bad code!", "name": "Ok Name"}, headers=h).status_code == 422
    assert client.post("/api/v1/suppliers", json={"code": "SUP-1", "name": "x"}, headers=h).status_code == 422
    r = client.post("/api/v1/suppliers", json={"code": "SUP-1", "name": "Good Supplier", "currency": "INR"}, headers=h)
    sid = r.json()["data"]["id"]
    # duplicate code => 409
    assert client.post("/api/v1/suppliers", json={"code": "SUP-1", "name": "Other"}, headers=h).status_code == 409
    # invalid status transition + archived restore blocked
    assert client.patch(f"/api/v1/suppliers/{sid}", json={"status": "bogus"}, headers=h).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{sid}", json={"status": "archived"}, headers=h).status_code == 200
    assert client.patch(f"/api/v1/suppliers/{sid}", json={"status": "active"}, headers=h).status_code == 422


def test_write_role_enforced_and_contacts(app_client):
    client, priv = app_client
    # token with unrelated role cannot write
    ro = _auth(priv, "t1", roles=("Read Only",))
    assert client.post("/api/v1/suppliers", json={"code": "SUP-R", "name": "Read Only Try"}, headers=ro).status_code == 403
    w = _auth(priv, "t1", roles=("Buyer",))
    sid = client.post("/api/v1/suppliers", json={"code": "SUP-C", "name": "Contact Corp"}, headers=w).json()["data"]["id"]
    rc = client.post(f"/api/v1/suppliers/{sid}/contacts", json={"full_name": "A Buyer"}, headers=w)
    assert rc.status_code == 201
    rl = client.get(f"/api/v1/suppliers/{sid}/contacts", headers=w)
    assert rl.json()["pagination"]["count"] == 1


def test_service_dedupe_hint():
    from app.core.tenant import reset_engine_cache
    from app.models.registry import Base
    from app.services.supplier import find_possible_duplicate
    from app.services.audit import record_event

    reset_engine_cache()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    record_event(db, tenant_id="t", actor="u", action="X", resource="r")
    from app.models.supplier import Supplier

    db.add(Supplier(tenant_id="t", created_by="u", updated_by="u", code="SUP-1", name="Acme Metals", country="IN"))
    db.flush()
    dup = find_possible_duplicate(db, tenant_id="t", name="acme metals", country="IN")
    assert dup != ""
    assert find_possible_duplicate(db, tenant_id="t", name="Other", country="IN") == ""
    db.close()
