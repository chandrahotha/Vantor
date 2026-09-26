"""Integration tests — adapter contract, webhook validation, HMAC fanout, tenant scope."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select

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
    bad = c.post("/api/v1/integrations", json={"name": "Mail", "itype": "email", "secret_ref": "notavaultref-must-be-refused-1"}, headers=h)
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
    from app.services.integration import Adapter, canonical, resolve_secret, sign

    body = canonical({"event": "ping", "n": 1})
    assert sign("s3cret", body) == sign("s3cret", body)
    assert sign("a", body) != sign("b", body)
    assert resolve_secret("env:DEFINITELY_NOT_SET_XYZ") == ""
    assert resolve_secret("notavaultref-must-be-refused-2") == ""
    with pytest.raises(NotImplementedError):
        Adapter().send("x", {})


def _seed_endpoints(tenant_id: str, urls: list[str]) -> None:
    from app.core.tenant import pinned_session
    from app.models.integration import WebhookEndpoint

    db = pinned_session(tenant_id)
    try:
        for url in urls:
            db.add(WebhookEndpoint(tenant_id=tenant_id, created_by="", updated_by="",
                                   url=url, events=["ping"], status="active",
                                   secret_ref="env:HOOK_KEY"))
        db.commit()
    finally:
        db.close()


def _fanout(tenant_id: str):
    """`fanout` only flushes — the caller owns the commit, exactly as the router does."""
    from app.core.tenant import pinned_session
    from app.services.integration import fanout

    db = pinned_session(tenant_id)
    try:
        out = fanout(db, tenant_id=tenant_id, event="ping", payload={"x": 1})
        db.commit()
        return out
    finally:
        db.close()


def test_duplicate_endpoint_urls_are_delivered_once(client, monkeypatch):
    """Two registrations of the same URL must not double-fire the consumer.

    `webhook_endpoints.url` carries no unique constraint (adding one is a schema
    change that could fail on existing rows), so a tenant could register the same
    endpoint twice and receive the same signed payload twice — a duplicate side
    effect for any consumer that is not idempotent. The extra registration is
    reported as `skipped_duplicate` rather than delivered.
    """
    from app.services import integration

    sent: list[str] = []

    class R:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(integration.httpx, "post", lambda url, **kw: (sent.append(url), R())[1])
    monkeypatch.setenv("HOOK_KEY", "s3cret")
    _seed_endpoints("t1", ["https://consumer.test/hook", "https://consumer.test/hook",
                           "https://other.test/hook"])

    out = _fanout("t1")
    assert sent.count("https://consumer.test/hook") == 1, sent
    assert sent.count("https://other.test/hook") == 1
    statuses = [o["status"] for o in out]
    assert statuses.count("skipped_duplicate") == 1
    assert statuses.count("delivered") == 2


def test_fanout_budget_defers_rather_than_holding_the_request(client, monkeypatch):
    """A slow endpoint must not pin the caller for the full per-endpoint timeout.

    Each delivery is a synchronous call with its own 10s timeout, so N dead
    endpoints held the request for 10s x N. Endpoints past the budget are
    recorded as `deferred` rather than silently dropped — a deferred attempt is
    a fact about this fanout and belongs in the audit trail.
    """
    from app.core.tenant import pinned_session
    from app.models.integration import WebhookDelivery
    from app.services import integration

    monkeypatch.setenv("HOOK_KEY", "s3cret")
    _seed_endpoints("t1", ["https://slow.test/hook"])
    # Zero budget: every endpoint is past its window. Patching the module
    # constant rather than `time.monotonic` — patching the clock would also
    # reach SQLAlchemy and the test framework.
    monkeypatch.setattr(integration, "FANOUT_BUDGET_S", 0.0)
    out = _fanout("t1")
    assert out[0]["status"] == "deferred"
    assert "budget" in out[0]["detail"]
    db = pinned_session("t1")
    try:
        rows = list(db.execute(select(WebhookDelivery)).scalars())
        assert [r.status for r in rows] == ["deferred"]
        assert "budget" in rows[0].last_error
    finally:
        db.close()
