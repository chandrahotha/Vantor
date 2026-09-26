"""Notifications tests — visibility, read marking, event emission."""
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
    jwk["kid"] = "nt-kid"
    from app.core import security

    security.override_jwks({"nt-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="buyer1", tenant="t1", roles=("Buyer", "Procurement Manager")):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "nt-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_badge_read_and_visibility(client):
    c, pem = client
    h = _h(pem)
    assert c.get("/api/v1/notifications/unread-count", headers=h).json()["data"]["unread"] == 0
    s = c.post("/api/v1/suppliers", json={"code": "SUP-N", "name": "Notify Co"}, headers=h).json()["data"]["id"]
    r = c.post("/api/v1/rfqs", json={"code": "RFQ-N", "title": "Widgets",
                "lines": [{"description": "Widget units", "quantity": 5}]}, headers=h).json()["data"]["id"]
    c.patch(f"/api/v1/rfqs/{r}/status", json={"status": "sent"}, headers=h)
    q = c.post(f"/api/v1/rfqs/{r}/quotes", json={"supplier_id": s, "lines": [{"unit_price_minor": 100, "quantity": 5}]}, headers=h).json()["data"]["id"]
    c.patch(f"/api/v1/rfqs/{r}/status", json={"status": "response"}, headers=h)
    c.patch(f"/api/v1/rfqs/{r}/status", json={"status": "evaluated"}, headers=h)
    assert c.post(f"/api/v1/rfqs/{r}/award", json={"quote_id": q, "reason": "only bid"}, headers=h).status_code == 201
    assert c.get("/api/v1/notifications/unread-count", headers=h).json()["data"]["unread"] == 1
    feed = c.get("/api/v1/notifications", headers=h).json()["data"]
    assert feed[0]["kind"] == "AWARD_DECIDED" and feed[0]["read"] is False
    nid = feed[0]["id"]
    assert c.post(f"/api/v1/notifications/{nid}/read", headers=h).json()["data"]["read"] is True
    assert c.get("/api/v1/notifications/unread-count", headers=h).json()["data"]["unread"] == 0
    assert c.get("/api/v1/notifications?unread=true", headers=h).json()["data"] == []
    # other tenant sees nothing
    assert c.get("/api/v1/notifications/unread-count", headers=_h(pem, "x", "other")).json()["data"]["unread"] == 0


def test_directed_notify_to_creator(client):
    c, pem = client
    h = _h(pem, "buyer9", "acme")
    s = c.post("/api/v1/suppliers", json={"code": "SUP-D", "name": "Directed"}, headers=h).json()["data"]["id"]
    po = c.post("/api/v1/purchase-orders", json={"code": "PO-D", "supplier_id": s,
                "lines": [{"description": "Bolt", "quantity": 2, "unit_price_minor": 100}]}, headers=h).json()["data"]["id"]
    mgr = _h(pem, "mgr9", "acme")
    assert c.post(f"/api/v1/purchase-orders/{po}/approve", headers=mgr).status_code == 200
    mine = c.get("/api/v1/notifications", headers=h).json()["data"]
    assert any(n["kind"] == "PO_APPROVED" for n in mine)
    assert c.get("/api/v1/notifications", headers=mgr).json()["data"] == []


def _award(c, pem, sub="buyer1", tenant="t1"):
    """Drive a full RFQ→award so a broadcast notification exists."""
    h = _h(pem, sub, tenant)
    s = c.post("/api/v1/suppliers", json={"code": f"SUP-{sub}", "name": "Components Co"}, headers=h).json()["data"]["id"]
    r = c.post("/api/v1/rfqs", json={"code": f"RFQ-{sub}", "title": "Widgets",
                "lines": [{"description": "Widget unit", "quantity": 5}]}, headers=h).json()["data"]["id"]
    c.patch(f"/api/v1/rfqs/{r}/status", json={"status": "sent"}, headers=h)
    q = c.post(f"/api/v1/rfqs/{r}/quotes", json={"supplier_id": s, "lines": [{"unit_price_minor": 100, "quantity": 5}]}, headers=h).json()["data"]["id"]
    c.patch(f"/api/v1/rfqs/{r}/status", json={"status": "response"}, headers=h)
    c.patch(f"/api/v1/rfqs/{r}/status", json={"status": "evaluated"}, headers=h)
    assert c.post(f"/api/v1/rfqs/{r}/award", json={"quote_id": q, "reason": "only bid"}, headers=h).status_code == 201
    return h


def test_broadcast_read_is_per_recipient(client):
    """One reader must not silence a broadcast alert for the rest of the tenant."""
    c, pem = client
    _award(c, pem)
    alice, bob = _h(pem, "alice", "t1"), _h(pem, "bob", "t1")
    assert c.get("/api/v1/notifications/unread-count", headers=alice).json()["data"]["unread"] == 1
    assert c.get("/api/v1/notifications/unread-count", headers=bob).json()["data"]["unread"] == 1
    nid = c.get("/api/v1/notifications", headers=alice).json()["data"][0]["id"]

    assert c.post(f"/api/v1/notifications/{nid}/read", headers=alice).json()["data"]["read"] is True
    # Alice is done, Bob is not — the regression this guards is the row-level
    # `read_at` that made the first reader clear it for everyone.
    assert c.get("/api/v1/notifications/unread-count", headers=alice).json()["data"]["unread"] == 0
    assert c.get("/api/v1/notifications/unread-count", headers=bob).json()["data"]["unread"] == 1
    assert c.get("/api/v1/notifications?unread=true", headers=bob).json()["data"][0]["id"] == nid
    assert c.get("/api/v1/notifications?unread=true", headers=alice).json()["data"] == []
    # marking twice is idempotent, not an error
    assert c.post(f"/api/v1/notifications/{nid}/read", headers=alice).status_code == 200


def test_directed_row_read_is_not_shared(client):
    """A directed row belongs to one user; it is never visible to another."""
    c, pem = client
    h = _h(pem, "creator", "t9")
    s = c.post("/api/v1/suppliers", json={"code": "SUP-X", "name": "Xavier"}, headers=h).json()["data"]["id"]
    po = c.post("/api/v1/purchase-orders", json={"code": "PO-X", "supplier_id": s,
                "lines": [{"description": "Bolt", "quantity": 1, "unit_price_minor": 10}]}, headers=h).json()["data"]["id"]
    other = _h(pem, "approver", "t9")
    assert c.post(f"/api/v1/purchase-orders/{po}/approve", headers=other).status_code == 200
    nid = c.get("/api/v1/notifications", headers=h).json()["data"][0]["id"]
    assert c.post(f"/api/v1/notifications/{nid}/read", headers=h).status_code == 200
    assert c.get("/api/v1/notifications/unread-count", headers=h).json()["data"]["unread"] == 0
    # 404 for someone it was never addressed to
    assert c.post(f"/api/v1/notifications/{nid}/read", headers=_h(pem, "stranger", "t9")).status_code == 404


def test_cursor_must_be_visible_to_caller(client):
    """A cursor from another user must not page relative to that row."""
    c, pem = client
    _award(c, pem, "alice", "t1")
    nid = c.get("/api/v1/notifications", headers=_h(pem, "alice", "t1")).json()["data"][0]["id"]
    # Same tenant, different subject: the row is a broadcast so it IS visible,
    # but a directed row belonging to someone else must 422, not page.
    other_tenant = _h(pem, "alice", "t2")
    assert c.get(f"/api/v1/notifications?cursor={nid}", headers=other_tenant).status_code == 422
    assert c.get(f"/api/v1/notifications?cursor={nid}", headers=_h(pem, "bob", "t1")).status_code == 200
