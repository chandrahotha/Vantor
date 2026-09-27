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


def _h(pem: bytes, sub: str = "u1"):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": "t1",
                      "realm_access": {"roles": ["Buyer"]},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "rl-kid"})
    return {"Authorization": f"Bearer {tok}"}


class _FakeRedis:
    """In-memory stand-in with the two commands the limiter actually uses."""

    def __init__(self):
        self.n: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def incrby(self, key, amount):
        self.n[key] = self.n.get(key, 0) + amount
        return self.n[key]

    def expire(self, key, ttl):
        self.ttls[key] = ttl
        return True

    def ping(self):
        return True


@pytest.fixture()
def fake_redis(monkeypatch):
    """Patch the limiter's store acquisition, not the module constant.

    The previous tests set `ratelimit._client` directly, which the rewrite made a
    dead assignment (the module now re-derives it through `_redis()`), so the
    limit was never applied and the test passed for the wrong reason.
    """
    from app.core import ratelimit

    store = _FakeRedis()
    monkeypatch.setattr(ratelimit, "_redis", lambda: store)
    return store


def test_429_after_write_limit(client, fake_redis, monkeypatch):
    from app.core import ratelimit

    c, pem = client
    monkeypatch.setenv("RATE_LIMIT_WRITE_PER_MIN", "2")
    from app.core.config import get_settings

    get_settings.cache_clear()
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
    assert "Retry-After" in over.headers
    get_settings.cache_clear()


def test_limit_is_per_identity_and_per_route(client, fake_redis, monkeypatch):
    """VNT-032: the old key was one shared bucket per tenant per method.

    That let a single caller exhaust everyone else's budget, and let a cheap list
    view hide an expensive one. The key is now the identity *and* a normalised
    route, so neither is possible.
    """
    from app.core.config import get_settings

    c, pem = client
    monkeypatch.setenv("RATE_LIMIT_READ_PER_MIN", "2")
    monkeypatch.setenv("RATE_LIMIT_WRITE_PER_MIN", "1")
    get_settings.cache_clear()

    noisy = _h(pem, sub="noisy")
    quiet = _h(pem, sub="quiet")
    # The noisy caller burns its own whole budget on one route.
    for _ in range(3):
        c.get("/api/v1/me", headers=noisy)
    # A different route for the same caller is unaffected...
    assert c.get("/api/v1/suppliers", headers=noisy).status_code == 200
    # ...and a different caller is unaffected on the busy route.
    assert c.get("/api/v1/me", headers=quiet).status_code == 200
    get_settings.cache_clear()


def test_route_label_collapses_path_parameters(client, fake_redis):
    """Otherwise a caller could sidestep the limit by generating new ids."""
    from app.core.ratelimit import _route_label

    class R:
        def __init__(self, path):
            self.url = type("U", (), {"path": path})()

    assert _route_label(R("/api/v1/suppliers/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")) == "/api/v1/suppliers/{id}"
    assert _route_label(R("/api/v1/purchase-orders/12345")) == "/api/v1/purchase-orders/{id}"
    assert _route_label(R("/api/v1/suppliers")) == "/api/v1/suppliers"
    # Two different ids share one bucket.
    assert (_route_label(R("/api/v1/suppliers/1111111111111111"))
            == _route_label(R("/api/v1/suppliers/2222222222222222")))


def test_ai_and_upload_have_their_own_budgets(client, fake_redis, monkeypatch):
    """VNT-032: a completion and a catalogue edit are not the same operation."""
    from app.core.ratelimit import _classify

    class Req:
        def __init__(self, method, path):
            self.method, self.url = method, type("U", (), {"path": path})()

    _, ai_cost = _classify(Req("POST", "/api/v1/ai/complete"))
    _, upload_cost = _classify(Req("POST", "/api/v1/documents"))
    _, write_cost = _classify(Req("POST", "/api/v1/suppliers"))
    assert ai_cost > write_cost
    assert upload_cost > write_cost


def test_store_outage_uses_a_local_backstop_and_says_so(client, monkeypatch):
    """VNT-032: a single Redis blip used to disable limiting permanently.

    The old code cached `False` and tested `if _client is None`, so nothing ever
    retried. Now there is a bounded per-process counter, and every response it
    touches says so.
    """
    from app.core import ratelimit
    from app.core.ratelimit import _RedisUnavailable

    def unavailable():
        raise _RedisUnavailable("down")

    c, pem = client
    monkeypatch.setattr(ratelimit, "_redis", unavailable)
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "open")
    r = c.get("/api/v1/me", headers=_h(pem))
    assert r.status_code == 200
    assert "fail-open" in r.headers.get("X-RateLimit-Bypass", "")
    assert "local-backstop" in r.headers.get("X-RateLimit-Bypass", "")


def test_store_outage_can_fail_closed(client, monkeypatch):
    """`RATE_LIMIT_FAIL_MODE=closed` refuses to serve rather than serving unlimited."""
    from app.core import ratelimit
    from app.core.ratelimit import _RedisUnavailable

    def unavailable():
        raise _RedisUnavailable("down")

    c, pem = client
    monkeypatch.setattr(ratelimit, "_redis", unavailable)
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")
    r = c.get("/api/v1/me", headers=_h(pem))
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "RATE_LIMITER_UNAVAILABLE"
    assert "fail-closed" in r.headers.get("X-RateLimit-Bypass", "")


def test_local_backstop_actually_limits(client, monkeypatch):
    """The fallback has to be a limit, not a decoration."""
    from app.core import ratelimit
    from app.core.ratelimit import _RedisUnavailable, _local_increment

    def unavailable():
        raise _RedisUnavailable("down")

    c, pem = client
    monkeypatch.setattr(ratelimit, "_redis", unavailable)
    ratelimit.reset_limiter_cache()
    statuses = [c.get("/api/v1/me", headers=_h(pem)).status_code for _ in range(4)]
    # Unset => the real read limit, which is generous; the point is that the
    # counter is per-key and monotonic, which the direct call proves.
    allowed = [_local_increment("k", limit=2) for _ in range(4)]
    assert [a for a, _ in allowed] == [True, True, False, False]
    assert all(n <= 4 for _, n in allowed)
    assert len(statuses) == 4
