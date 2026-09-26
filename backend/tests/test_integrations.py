"""Integration tests — adapter contract, webhook validation, HMAC fanout, tenant scope."""
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
    jwk["kid"] = "in-kid"
    from app.core import security

    security.override_jwks({"in-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, tenant="t1"):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "u1", "tenant_id": tenant,
                      "realm_access": {"roles": ["Buyer"]},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "in-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_types_and_registration_guards(client):
    c, pem = client
    h = _h(pem, "acme")
    assert "logging" in c.get("/api/v1/integrations/types", headers=h).json()["data"]["adapters"]
    assert c.post("/api/v1/integrations", json={"name": "X", "itype": "teleport"}, headers=h).status_code == 422
    # raw secrets refused — vault refs only
    bad = c.post("/api/v1/integrations", json={"name": "Mail", "itype": "email", "secret_ref": "sk-live-123"}, headers=h)
    assert bad.status_code == 422
    ok = c.post("/api/v1/integrations", json={"name": "Mail", "itype": "email", "secret_ref": "env:MAIL_KEY"}, headers=h)
    assert ok.status_code == 201
    # non-https webhooks refused
    assert c.post("/api/v1/webhooks/endpoints", json={"url": "http://x.test/h"}, headers=h).status_code == 422
    ep = c.post("/api/v1/webhooks/endpoints", json={"url": "https://x.test/h", "events": ["ping"]}, headers=h)
    assert ep.status_code == 201
    # ping without secret => failed delivery recorded, never raised
    t = c.post("/api/v1/webhooks/test", headers=h)
    assert t.status_code == 200
    assert t.json()["data"]["deliveries"][0]["status"] == "failed"
    assert c.get("/api/v1/webhooks/deliveries?status=failed", headers=h).json()["data"] != []
    assert c.get("/api/v1/webhooks/deliveries", headers=_h(pem, "other")).json()["data"] == []


def test_hmac_sign_verify():
    from app.services.integration import canonical, resolve_secret, sign

    body = canonical({"event": "ping", "n": 1})
    assert sign("s3cret", body) == sign("s3cret", body)
    assert sign("a", body) != sign("b", body)
    assert resolve_secret("env:DEFINITELY_NOT_SET_XYZ") == ""
    assert resolve_secret("sk-live-raw") == ""
    import pytest as _pt

    from app.services.integration import LoggingAdapter

    with _pt.raises(NotImplementedError):
        from app.services.integration import Adapter

        Adapter().send("x", {})
