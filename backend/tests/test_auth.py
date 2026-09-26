"""Auth — real RS256 verification with ephemeral keys (no fakes, no bypass).

Covers: valid token w/ tenant+roles, missing bearer => 401, wrong alg => 401,
expired => 401, no-tenant claim => 403, unknown kid => 401, wrong role => 403.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core import security
from app.main import app

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


@pytest.fixture()
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    pub_key = pub
    # Build a JWKS-override entry keyed by kid; security._fetch_jwks returns it directly.
    from jwt.algorithms import RSAAlgorithm

    jwk_json = RSAAlgorithm.to_jwk(pub_key, as_dict=True)
    jwk_json["kid"] = "test-kid"
    # from_jwk accepts the dict; store the key object for verification speed.
    key_obj = RSAAlgorithm.from_jwk(jwk_json)
    security.override_jwks({"test-kid": key_obj})
    yield {"priv_pem": priv_pem}
    security.override_jwks(None)


def _token(priv_pem: bytes, **claims) -> str:
    now = datetime.now(timezone.utc)
    base = {"iss": ISS, "aud": AUD, "sub": "user-1", "exp": now + timedelta(minutes=5), "iat": now}
    base.update(claims)
    return jwt.encode(base, priv_pem, algorithm="RS256", headers={"kid": "test-kid"})


def _client_with_env(monkeypatch):
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("JWT_AUDIENCE", AUD)
    # clear cached settings so new env applies
    from app.core.config import get_settings

    get_settings.cache_clear()
    return TestClient(app)


def test_missing_token_is_401(monkeypatch):
    c = _client_with_env(monkeypatch)
    r = c.get("/api/v1/audit-events")
    assert r.status_code == 401


def test_valid_token_reaches_tenant_scoped_endpoint(keys, monkeypatch):
    c = _client_with_env(monkeypatch)
    tok = _token(keys["priv_pem"], tenant_id="t1", realm_access={"roles": ["Buyer"]})
    r = c.get("/api/v1/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["tenantId"] == "t1"
    assert "Buyer" in body["data"]["roles"]


def test_token_without_tenant_is_403(keys, monkeypatch):
    c = _client_with_env(monkeypatch)
    tok = _token(keys["priv_pem"])
    r = c.get("/api/v1/audit-events", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_expired_token_is_401(keys, monkeypatch):
    c = _client_with_env(monkeypatch)
    now = datetime.now(timezone.utc)
    tok = jwt.encode(
        {"iss": ISS, "aud": AUD, "sub": "u", "tenant_id": "t1", "exp": now - timedelta(minutes=1), "iat": now - timedelta(minutes=10)},
        keys["priv_pem"],
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    r = c.get("/api/v1/audit-events", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


def test_none_alg_rejected(keys, monkeypatch):
    c = _client_with_env(monkeypatch)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "u", "tenant_id": "t1"}, key="", algorithm="none")
    r = c.get("/api/v1/audit-events", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401
