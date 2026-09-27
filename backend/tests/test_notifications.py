"""Notifications tests — visibility, read marking, event emission.

Sourcing setup goes through `helpers.seed_rfq_award` because an award needs a
qualified supplier and a line-mapped, currency-matched quote (VNT-020/VNT-021).
None of these tests are about sourcing — they just need an `AWARD_DECIDED`
broadcast to have happened.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from .helpers import drain_notifications, open_rfq_for_bid, seed_rfq_award, submit_bid

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


def _h(pem: bytes, sub="buyer1", tenant="t1",
       roles=("Buyer", "Procurement Manager", "Compliance Reviewer")):
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
    rfq, line, supplier = open_rfq_for_bid(c, h, code="RFQ-N", title="Widgets",
                                           line_desc="Widget units", quantity=5,
                                           reviewer_h=_h(pem, "reviewer", "t1"))
    # Onboarding legitimately emits notifications, so the baseline is cleared
    # before the award. Asserting an exact unread count against a count that
    # drifts every time the supplier flow grows a step is how badge tests rot.
    drain_notifications(c, h)
    assert c.get("/api/v1/notifications/unread-count", headers=h).json()["data"]["unread"] == 0
    submit_bid(c, h, rfq, line, supplier, quantity=5, unit_price_minor=100)
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
    """Drive a full RFQ→award and leave exactly one unread broadcast behind.

    Onboarding (certification verified, qualification decided) emits its own
    notifications, so the feed is drained immediately before the award. Every
    caller of this helper then gets a clean baseline of one unread, which is what
    makes an exact badge assertion possible.
    """
    h = _h(pem, sub, tenant)
    rfq, line, supplier = open_rfq_for_bid(
        c, h, code=f"RFQ-{sub}", title="Widgets", line_desc="Widget unit",
        quantity=5, reviewer_h=_h(pem, "reviewer", tenant))
    drain_notifications(c, h)
    submit_bid(c, h, rfq, line, supplier, quantity=5, unit_price_minor=100)
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


def _seed_broadcasts(c, pem, tenant, count):
    """Insert `count` broadcast rows already read by both readers."""
    from app.core.tenant import pinned_session
    from app.models.notification import Notification

    db = pinned_session(tenant)
    try:
        for i in range(count):
            db.add(Notification(tenant_id=tenant, created_by="seed", updated_by="seed",
                                user_sub="", kind="SEED", title=f"seed {i}", body="",
                                link="", read_at="", read_by=["alice", "bob"]))
        db.commit()
    finally:
        db.close()


def test_unread_page_never_reports_hasmore_false_while_rows_remain(client):
    """A short unread page must not hide the rest behind `hasMore: false`.

    The feed over-fetches (4x) and then filters read-state in Python, because
    `read_by` is a JSON array with no portable "does not contain". Two bugs met
    here: when the over-fetch filled up, the rows it discarded may well have
    contained unread items and `hasMore` still said false; and when that filter
    emptied the page there was no returned row left to anchor a cursor to, so
    `hasMore: true` came with no `nextCursor` and the UI could not page out of
    it at all.
    """
    c, pem = client
    _award(c, pem, "alice", "t1")
    # 120 read broadcasts (limit 25 => 100-row over-fetch) plus one unread
    # award at the very bottom. The award is outside the over-fetch window, so
    # the first page is legitimately empty — but it must advertise a next page
    # and hand back a usable cursor.
    _seed_broadcasts(c, pem, "t1", 120)
    alice = _h(pem, "alice", "t1")
    page = c.get("/api/v1/notifications?unread=true&limit=25", headers=alice).json()
    assert page["data"] == []
    assert page["pagination"]["hasMore"] is True
    assert page["pagination"]["nextCursor"], "hasMore without a cursor is a dead end"
    # and following the cursor actually reaches the unread award
    page2 = c.get(f"/api/v1/notifications?unread=true&limit=25&cursor={page['pagination']['nextCursor']}",
                  headers=alice).json()
    assert any(n["kind"] == "AWARD_DECIDED" for n in page2["data"]), page2


def test_badge_does_not_grow_without_bound(client):
    """The badge scans broadcast read-state in Python, so it is capped.

    Past the cap the count is reported with `unreadCapped` rather than being
    silently truncated, so the UI can say "50+" instead of showing a wrong
    number.
    """
    from app.routers.notifications import BROADCAST_SCAN_CAP

    c, pem = client
    _award(c, pem, "alice", "t1")
    alice = _h(pem, "alice", "t1")
    d = c.get("/api/v1/notifications/unread-count", headers=alice).json()["data"]
    assert d["unread"] == 1 and d["unreadCapped"] is False

    _seed_broadcasts(c, pem, "t1", BROADCAST_SCAN_CAP)
    d2 = c.get("/api/v1/notifications/unread-count", headers=alice).json()["data"]
    assert d2["unreadCapped"] is True
    # bob has read all of those, so his count is not inflated by them
    assert c.get("/api/v1/notifications/unread-count", headers=_h(pem, "bob", "t1")).json()["data"]["unreadCapped"] is True
