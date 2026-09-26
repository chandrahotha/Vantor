"""Onboarding tests — certs, evidence-gated submit, SoD decide, activation."""
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
    jwk["kid"] = "ob-kid"
    from app.core import security

    security.override_jwks({"ob-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="buyer1", tenant="t1"):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": ["Supplier Manager"]},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "ob-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_full_onboarding_flow(client):
    c, pem = client
    h = _h(pem)
    sid = c.post("/api/v1/suppliers", json={"code": "SUP-OB", "name": "Onboard Me"}, headers=h).json()["data"]["id"]
    # submit with no evidence => submitted (not under_review)
    assert c.post(f"/api/v1/suppliers/{sid}/qualification/submit", headers=h).json()["data"]["status"] == "submitted"
    # decide blocked before review
    assert c.post(f"/api/v1/suppliers/{sid}/qualification/decide", json={"decision": "qualified"}, headers=_h(pem, sub="mgr")).status_code == 422
    # add + verify cert, add B scorecard
    cert = c.post(f"/api/v1/suppliers/{sid}/certifications", json={"name": "ISO 9001", "issuer": "BSI", "valid_until": "2027-01-01"}, headers=h).json()["data"]["id"]
    assert c.post(f"/api/v1/suppliers/{sid}/certifications/{cert}/verify", headers=h).status_code == 200
    dims = {"quality": 700, "delivery": 700, "price": 700, "compliance": 700, "responsiveness": 700}
    assert c.post(f"/api/v1/suppliers/{sid}/scorecard", json={"dims": dims}, headers=h).json()["data"]["grade"] == "B"
    # rejected case resubmits: first decide path needs under_review — resubmit now auto-advances
    # (previous submit row is in submitted; resubmit blocked? submitted not in draft/rejected => 422, so decide flow uses fresh supplier)
    sid2 = c.post("/api/v1/suppliers", json={"code": "SUP-OB2", "name": "Onboard Two"}, headers=h).json()["data"]["id"]
    c.post(f"/api/v1/suppliers/{sid2}/certifications", json={"name": "ISO 14001"}, headers=h)
    certs = c.get(f"/api/v1/suppliers/{sid2}/certifications", headers=h).json()["data"]
    c.post(f"/api/v1/suppliers/{sid2}/certifications/{certs[0]['id']}/verify", headers=h)
    c.post(f"/api/v1/suppliers/{sid2}/scorecard", json={"dims": dims}, headers=h)
    st = c.post(f"/api/v1/suppliers/{sid2}/qualification/submit", headers=h).json()["data"]["status"]
    assert st == "under_review"
    # submitter cannot decide own case
    assert c.post(f"/api/v1/suppliers/{sid2}/qualification/decide", json={"decision": "qualified"}, headers=h).status_code == 403
    mgr = _h(pem, sub="mgr1")
    assert c.post(f"/api/v1/suppliers/{sid2}/qualification/decide", json={"decision": "qualified", "reason": "evidence complete"}, headers=mgr).json()["data"]["status"] == "qualified"
    # qualified draft supplier becomes active
    assert c.get(f"/api/v1/suppliers/{sid2}", headers=h).json()["data"]["status"] == "active"
    assert c.get(f"/api/v1/suppliers/{sid2}/qualification", headers=_h(pem, tenant="other")).status_code == 404
