"""QA regression tests — fail-closed authz + envelope shape (HIGH findings)."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


@pytest.fixture()
def client(monkeypatch):
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
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "qa-kid"
    from app.core import security

    security.override_jwks({"qa-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _tok(pem: bytes, roles=(), tenant="t1", sub="u1"):
    now = datetime.now(timezone.utc)
    claims = {"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
              "exp": now + timedelta(minutes=5), "iat": now}
    if roles:
        claims["realm_access"] = {"roles": list(roles)}
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": "qa-kid"})


def test_empty_roles_cannot_write(client):
    c, pem = client
    h = {"Authorization": f"Bearer {_tok(pem, roles=())}"}
    r = c.post("/api/v1/suppliers", json={"code": "SUP-Z", "name": "No Role Corp"}, headers=h)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_envelope_shape_on_auth_errors(client):
    c, pem = client
    r = c.get("/api/v1/suppliers/does-not-exist", headers={"Authorization": f"Bearer {_tok(pem, roles=('Buyer',))}"})
    assert r.status_code == 404
    body = r.json()
    assert set(body.keys()) == {"data", "pagination", "error", "requestId"}
    assert body["data"] is None and body["error"]["code"] == "NOT_FOUND"
    r2 = c.get("/api/v1/suppliers")
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "UNAUTHORIZED"


def test_read_only_cannot_approve(client):
    c, pem = client
    w = {"Authorization": f"Bearer {_tok(pem, roles=('Buyer',), sub='buyer1')}"}
    ro = {"Authorization": f"Bearer {_tok(pem, roles=('Read Only',), sub='ro1')}"}
    s = c.post("/api/v1/suppliers", json={"code": "SUP-Q", "name": "Q Corp"}, headers=w).json()["data"]["id"]
    po = c.post("/api/v1/purchase-orders", json={"code": "PO-Q", "supplier_id": s, "lines": [{"description": "Bolt", "quantity": 1, "unit_price_minor": 100}]}, headers=w)
    pid = po.json()["data"]["id"]
    assert c.post(f"/api/v1/purchase-orders/{pid}/approve", headers=ro).status_code == 403


def test_idempotency_replay(client):
    c, pem = client
    h = {"Authorization": f"Bearer {_tok(pem, roles=('Buyer',))}", "Idempotency-Key": "k-123"}
    r1 = c.post("/api/v1/suppliers", json={"code": "SUP-I", "name": "Idem Corp"}, headers=h)
    assert r1.status_code == 201
    r2 = c.post("/api/v1/suppliers", json={"code": "SUP-I", "name": "Idem Corp"}, headers=h)
    assert r2.status_code == 201
    assert r2.json()["data"]["id"] == r1.json()["data"]["id"]
