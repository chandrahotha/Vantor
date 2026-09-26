"""Rate limiter tests — 429 envelope, fail-open without Redis."""
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
    jwk["kid"] = "rl-kid"
    from app.core import security

    security.override_jwks({"rl-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()
    from app.core import ratelimit

    ratelimit.reset_limiter_cache()


def _h(pem: bytes):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "u1", "tenant_id": "t1",
                      "realm_access": {"roles": ["Buyer"]},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "rl-kid"})
    return {"Authorization": f"Bearer {tok}"}


class _FakeRedis:
    def __init__(self):
        self.n = {}

    def incr(self, k):
        self.n[k] = self.n.get(k, 0) + 1
        return self.n[k]

    def expire(self, k, s):
        return True


def test_429_after_write_limit(client, monkeypatch):
    from app.core import ratelimit

    c, pem = client
    monkeypatch.setattr(ratelimit, "WRITE_LIMIT", 2)
    monkeypatch.setattr(ratelimit, "_client", _FakeRedis())
    h = _h(pem)
    assert c.get("/api/v1/me", headers=h).status_code == 200
    r = c.get("/api/v1/me", headers=h)
    assert r.status_code == 200
    assert "X-RateLimit-Remaining" in r.headers
    # writes limited to 2/min in this test
    assert c.post("/api/v1/suppliers", json={"code": "RL-1", "name": "RL One"}, headers=h).status_code == 201
    assert c.post("/api/v1/suppliers", json={"code": "RL-2", "name": "RL Two"}, headers=h).status_code == 201
    over = c.post("/api/v1/suppliers", json={"code": "RL-3", "name": "RL Three"}, headers=h)
    assert over.status_code == 429
    assert over.json()["error"]["code"] == "RATE_LIMITED"


def test_fail_open_without_redis(client, monkeypatch):
    from app.core import ratelimit

    c, pem = client
    monkeypatch.setattr(ratelimit, "_client", False)
    monkeypatch.setattr(ratelimit, "_redis", lambda: None)
    r = c.get("/api/v1/me", headers=_h(pem))
    assert r.status_code == 200
    assert r.headers.get("X-RateLimit-Bypass") == "limiter-unavailable"
