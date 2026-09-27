"""Demo mode: how a bare machine boots the app without Keycloak.

The reviewer walks in as a signed demo actor (name `.sig`), carrying the same
roles it'd have if they'd signed in. Writes are carefully gated: nothing that
makes a *submission* (supplier form, quote entry) is reachable.
"""
import hashlib
import hmac as _hmac

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


@pytest.fixture()
def demo_client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'demo.db'}")
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("JWT_AUDIENCE", AUD)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_TOKEN", "test-demo-key")

    from app.core.config import get_settings
    from app.core.tenant import get_engine, reset_engine_cache

    get_settings.cache_clear()
    reset_engine_cache()
    from app.models.registry import Base

    Base.metadata.create_all(get_engine())

    from app.main import app as fastapi_app

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "demo-kid"
    from app.core import security
    security.override_jwks({"demo-kid": RSAAlgorithm.from_jwk(jwk)})

    yield TestClient(fastapi_app, raise_server_exceptions=False)

    security.override_jwks(None)
    reset_engine_cache()
    get_settings.cache_clear()


def _sig(name: str) -> str:
    return _hmac.new(b"test-demo-key", name.encode(), hashlib.sha256).hexdigest()


def _tok(name: str, sig: str) -> dict:
    return {"Authorization": f"Bearer demo:{name}.{sig}"}


def test_demo_actor_read_only_and_Blocks_writes(demo_client):
    c = demo_client
    t = _tok("demo.user", _sig("demo.user"))

    for p in ("/api/v1/suppliers", "/api/v1/purchase-orders",
              "/api/v1/rfqs", "/api/v1/contracts"):
        assert c.get(p, headers=t).status_code == 200

    # And writing is 403. That's the demo mode promise: it cannot be extended
    # to a material change without a real session.
    r = c.post("/api/v1/suppliers", json={"code": "S-P", "name": "NewCo"}, headers=t)
    assert r.status_code == 403

    po = c.post("/api/v1/purchase-orders", json={"code": "PO-G1", "supplier_id": "x",
                   "lines": [{"description": "Forged part", "quantity": 1, "unit_price_minor": 10}]}, headers=t)
    assert po.status_code in (403, 422)


def test_production_refuses_demo_mode(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_TOKEN", "x")
    from app.core.config import Settings

    with pytest.raises(RuntimeError, match="must never boot"):
        Settings().require_prod_secrets()
