"""AI gateway + tools tests — evidence contract, no silent fallback, tenant scoping."""
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
    monkeypatch.setenv("AI_PROVIDER", "disabled")
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
    jwk["kid"] = "ai-kid"
    from app.core import security

    security.override_jwks({"ai-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, tenant="t1", roles=("Buyer",)):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "u1", "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "ai-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_disabled_mode_honest_envelope(client):
    c, pem = client
    r = c.post("/api/v1/ai/complete", json={"prompt": "Summarize spend"}, headers=_h(pem))
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["confidence"] == 0.0 and body["requires_human_review"] is True
    assert "UNKNOWN" in body["answer"] and body["provider"] == "disabled"


def test_unknown_provider_names_itself(client):
    c, pem = client
    r = c.post("/api/v1/ai/complete", json={"prompt": "hi there", "provider": "oracle-ai"}, headers=_h(pem))
    assert r.status_code == 502
    assert r.json()["error"]["details"]["provider"] == "oracle-ai"


def test_unconfigured_opencode_fails_explicitly(client):
    c, pem = client
    r = c.post("/api/v1/ai/complete", json={"prompt": "hello world", "provider": "opencode"}, headers=_h(pem))
    assert r.status_code == 502
    assert "opencode" in r.json()["error"]["message"].lower()


def test_tools_tenant_scoped_and_audited(client):
    c, pem = client
    c.post("/api/v1/suppliers", json={"code": "SUP-AI", "name": "AI Parts"}, headers=_h(pem, "ta"))
    r = c.post("/api/v1/ai/tools/search_suppliers", json={"q": "AI", "limit": 5}, headers=_h(pem, "ta"))
    assert r.status_code == 200
    assert len(r.json()["data"]["result"]["suppliers"]) == 1
    assert r.json()["data"]["requiresHumanReview"] is True
    # other tenant sees nothing
    r2 = c.post("/api/v1/ai/tools/search_suppliers", json={"q": "AI"}, headers=_h(pem, "tb"))
    assert r2.json()["data"]["result"]["suppliers"] == []
    # unknown tool 404, role-less token 403
    assert c.post("/api/v1/ai/tools/drop_tables", json={}, headers=_h(pem, "ta")).status_code == 404
    now2 = datetime.now(timezone.utc)
    roleless = jwt.encode({"iss": ISS, "aud": AUD, "sub": "u", "tenant_id": "ta",
                           "exp": now2 + timedelta(minutes=5), "iat": now2},
                          pem, algorithm="RS256", headers={"kid": "ai-kid"})
    assert c.post("/api/v1/ai/tools/search_suppliers", json={"q": "x"},
                  headers={"Authorization": f"Bearer {roleless}"}).status_code == 403
