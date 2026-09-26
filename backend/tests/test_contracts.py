"""Contract Wave 2.3 tests — lifecycle, real calendar dates, obligations, expiry roll."""
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
    jwk["kid"] = "c-kid"
    from app.core import security

    security.override_jwks({"c-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, tenant="t1"):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "legal1", "tenant_id": tenant,
                      "realm_access": {"roles": ["Legal Reviewer"]},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "c-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_contract_lifecycle_dates_obligations(client):
    c, pem = client
    h = _h(pem, "acme")
    # impossible calendar date rejected (real validation, not string compare)
    bad = c.post("/api/v1/contracts", json={"code": "CT-1", "title": "Bad dates", "start_date": "2026-02-30", "end_date": "2026-03-01"}, headers=h)
    assert bad.status_code == 422
    inv = c.post("/api/v1/contracts", json={"code": "CT-1", "title": "Inverted", "start_date": "2026-05-01", "end_date": "2026-04-01"}, headers=h)
    assert inv.status_code == 422
    r = c.post("/api/v1/contracts", json={"code": "CT-1", "title": "Steel supply", "currency": "INR", "value_minor": 5000000,
                                          "start_date": "2026-01-01", "end_date": "2026-12-31"}, headers=h)
    assert r.status_code == 201, r.text
    cid = r.json()["data"]["id"]
    assert c.post("/api/v1/contracts", json={"code": "CT-1", "title": "Dup"}, headers=h).status_code == 409
    # lifecycle: draft->active illegal (must go via review)
    assert c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=h).status_code == 422
    assert c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=h).status_code == 200
    assert c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=h).status_code == 200
    o = c.post(f"/api/v1/contracts/{cid}/obligations", json={"title": "Quarterly audit", "due_date": "2026-06-30", "owner": "Legal"}, headers=h)
    assert o.status_code == 201, o.text
    got = c.get(f"/api/v1/contracts/{cid}", headers=h).json()["data"]
    assert got["obligationCount"] == 1
    assert c.get("/api/v1/contracts", headers=_h(pem, "other")).json()["data"] == []


def test_expiry_roll_and_service_rules():
    from datetime import date
    from app.services.contract import check_transition, is_due_expiring, parse_iso_day
    import pytest as _pt

    with _pt.raises(Exception):
        parse_iso_day("2026-02-30", "end_date")
    with _pt.raises(Exception):
        check_transition("draft", "active")
    today = date(2026, 9, 26)
    assert is_due_expiring("active", "2026-12-01", today) is True
    assert is_due_expiring("active", "2027-06-01", today) is False
    assert is_due_expiring("draft", "2026-10-01", today) is False
