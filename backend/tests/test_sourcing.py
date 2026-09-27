"""Sourcing Wave 2.2 tests — RFQ lifecycle, quotes, comparison, award, tenant isolation.

The fixture setup qualifies its suppliers on purpose. VNT-020/VNT-021 made two
things real controls that used to be decorative: a quote must cite an RFQ line and
carry the RFQ's currency, and only a supplier that is `active` and holds a
`qualified` qualification may bid at all. A test that submits a quote from a bare
`draft` supplier with no line mapping was asserting the buggy behaviour, so it
now sets up the supplier a real buyer would.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from .helpers import REVIEWER_ROLES, qualified_supplier, rfq_line_ids

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
    jwk["kid"] = "s-kid"
    from app.core import security

    security.override_jwks({"s-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, tenant="t1", sub="buyer1", roles=("Buyer",)):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "s-kid"})
    return {"Authorization": f"Bearer {tok}"}


def _supplier(c, pem, tenant, code, name):
    """A supplier that is legally allowed to bid."""
    return qualified_supplier(c, _h(pem, tenant), code, name,
                              reviewer_h=_h(pem, tenant, sub="reviewer1", roles=REVIEWER_ROLES))

def test_rfq_quote_award_flow(client):
    c, pem = client
    h = _h(pem, "acme")
    s1 = _supplier(c, pem, "acme", "SUP-A", "Alpha Metals")
    s2 = _supplier(c, pem, "acme", "SUP-B", "Beta Steels")
    r = c.post("/api/v1/rfqs", json={"code": "RFQ-001", "title": "Steel plates", "currency": "INR",
                                     "lines": [{"description": "Plate 10mm", "quantity": 100}, {"description": "Plate 20mm", "quantity": 50}]}, headers=h)
    assert r.status_code == 201, r.text
    rfq = r.json()["data"]["id"]
    l1, l2 = rfq_line_ids(c, h, rfq)
    # quotes rejected before RFQ sent
    bad = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": s1, "lines": [{"rfq_line_id": l1, "unit_price_minor": 50000, "quantity": 100}]}, headers=h)
    assert bad.status_code == 422
    assert c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "sent"}, headers=h).status_code == 200
    # VNT-021: a quote in a different currency from the RFQ is refused outright.
    wrong_ccy = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": s1, "currency": "USD",
                      "lines": [{"rfq_line_id": l1, "unit_price_minor": 50000, "quantity": 100}]}, headers=h)
    assert wrong_ccy.status_code == 422 and wrong_ccy.json()["error"]["code"] == "QUOTE_CURRENCY_MISMATCH"
    # VNT-020: a line with no rfq_line_id is refused -- it used to be accepted and
    # silently vanish from the coverage check that decides whether a bid is complete.
    unmapped = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": s1,
                      "lines": [{"unit_price_minor": 50000, "quantity": 100}]}, headers=h)
    assert unmapped.status_code == 422 and unmapped.json()["error"]["code"] == "QUOTE_LINE_NOT_ON_RFQ"
    q1 = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": s1, "lines": [{"rfq_line_id": l1, "unit_price_minor": 50000, "quantity": 100}, {"rfq_line_id": l2, "unit_price_minor": 90000, "quantity": 50}]}, headers=h)
    assert q1.status_code == 201, q1.text
    assert q1.json()["data"]["totalMinor"] == 50000 * 100 + 90000 * 50
    q2 = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": s2, "lines": [{"rfq_line_id": l1, "unit_price_minor": 40000, "quantity": 100}, {"rfq_line_id": l2, "unit_price_minor": 80000, "quantity": 50}]}, headers=h)
    assert q2.status_code == 201
    # duplicate quote per supplier rejected
    assert c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": s1, "lines": [{"rfq_line_id": l1, "unit_price_minor": 1, "quantity": 1}]}, headers=h).status_code == 409
    # comparison sorted cheapest first with real totals
    comp = c.get(f"/api/v1/rfqs/{rfq}/comparison", headers=h).json()["data"]
    assert comp[0]["supplierId"] == s2 and comp[1]["supplierId"] == s1
    # award requires evaluated (RFQ auto-moved sent->response on first quote)
    assert c.post(f"/api/v1/rfqs/{rfq}/award", json={"quote_id": q2.json()["data"]["id"]}, headers=h).status_code == 422
    assert c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "evaluated"}, headers=h).status_code == 200
    # illegal jump draft->awarded blocked at service level (covered) — award now
    a = c.post(f"/api/v1/rfqs/{rfq}/award", json={"quote_id": q2.json()["data"]["id"], "reason": "Lowest evaluated total"}, headers=h)
    assert a.status_code == 201, a.text
    assert a.json()["data"]["awardedTotalMinor"] == 40000 * 100 + 80000 * 50
    # second award rejected; rfq shows awarded
    assert c.post(f"/api/v1/rfqs/{rfq}/award", json={"quote_id": q1.json()["data"]["id"]}, headers=h).status_code == 409
    got = c.get(f"/api/v1/rfqs/{rfq}", headers=h).json()["data"]
    assert got["status"] == "awarded"


def test_unqualified_supplier_cannot_bid(client):
    """VNT-020: eligibility is enforced at bid submission, not at evaluation.

    Before, `submit_quote` checked only tenant membership, so a `draft` supplier
    with no certification and no qualification could submit a bid and - once
    evaluation did nothing - win the award. The bid is now refused outright.
    """
    c, pem = client
    h = _h(pem, "acme")
    reviewer = _h(pem, "acme", sub="reviewer1", roles=REVIEWER_ROLES)
    bare = c.post("/api/v1/suppliers", json={"code": "SUP-BARE", "name": "Bare Ltd"}, headers=h).json()["data"]["id"]
    good = qualified_supplier(c, h, "SUP-GOOD", "Good Ltd", reviewer_h=reviewer)
    rfq = c.post("/api/v1/rfqs", json={"code": "RFQ-ELIG", "title": "Eligibility", "currency": "INR",
                                       "lines": [{"description": "Bolt", "quantity": 5}]}, headers=h).json()["data"]["id"]
    (l1,) = rfq_line_ids(c, h, rfq)
    c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "sent"}, headers=h)
    draft_bid = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": bare,
                       "lines": [{"rfq_line_id": l1, "unit_price_minor": 100, "quantity": 5}]}, headers=h)
    assert draft_bid.status_code == 422 and draft_bid.json()["error"]["code"] == "SUPPLIER_NOT_ACTIVE"
    ok = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": good,
                "lines": [{"rfq_line_id": l1, "unit_price_minor": 100, "quantity": 5}]}, headers=h)
    assert ok.status_code == 201, ok.text


def test_evaluation_refuses_incomplete_bids(client):
    """VNT-020: an RFQ cannot be evaluated while an RFQ line is priced by nobody."""
    c, pem = client
    h = _h(pem, "acme")
    s = _supplier(c, pem, "acme", "SUP-PART", "Partial Ltd")
    rfq = c.post("/api/v1/rfqs", json={"code": "RFQ-PART", "title": "Partial", "currency": "INR",
                                       "lines": [{"description": "Line A", "quantity": 5}, {"description": "Line B", "quantity": 7}]},
                 headers=h).json()["data"]["id"]
    l1, l2 = rfq_line_ids(c, h, rfq)
    c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "sent"}, headers=h)
    q = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": s,
                "lines": [{"rfq_line_id": l1, "unit_price_minor": 100, "quantity": 5}]}, headers=h)
    assert q.status_code == 201, q.text
    c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "response"}, headers=h)
    blocked = c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "evaluated"}, headers=h)
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "RFQ_LINES_UNPRICED"
    assert blocked.json()["error"]["details"]["unpricedCount"] == 1


def test_award_records_real_savings(client):
    """Awarding the cheaper quote must record the gap as savings.

    The savings baseline used to be computed *after* the losers were flipped to
    `rejected`, and the re-query only asked for `evaluated|awarded` — so the
    comparison set was the winner alone and every award recorded zero savings.
    This is the number the savings engine and the copilot both report on.
    """
    c, pem = client
    h = _h(pem, "acme")
    s1 = _supplier(c, pem, "acme", "SUP-HI", "Pricy Metals")
    s2 = _supplier(c, pem, "acme", "SUP-LO", "Cheap Metals")
    rfq = c.post("/api/v1/rfqs", json={"code": "RFQ-SAV", "title": "Savings", "currency": "INR",
                                      "lines": [{"description": "Bolt", "quantity": 10}]}, headers=h).json()["data"]["id"]
    (l1,) = rfq_line_ids(c, h, rfq)
    c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "sent"}, headers=h)
    hi = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": s1,
                 "lines": [{"rfq_line_id": l1, "unit_price_minor": 10_000, "quantity": 10}]}, headers=h).json()["data"]["id"]
    lo = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": s2,
                 "lines": [{"rfq_line_id": l1, "unit_price_minor": 7_000, "quantity": 10}]}, headers=h).json()["data"]["id"]
    c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "evaluated"}, headers=h)
    r = c.post(f"/api/v1/rfqs/{rfq}/award", json={"quote_id": lo, "reason": "cheaper"}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["data"]["awardedTotalMinor"] == 70_000

    saved = c.post("/api/v1/ai/tools/calculate_savings", json={}, headers=h).json()["data"]["result"]
    assert saved["savedMinor"] == 30_000, saved
    assert saved["awards"] == 1
    # the loser is rejected and the winner awarded, and the comparison view
    # (which the award decision is made from) is still coherent
    comp = {row["quoteId"]: row for row in c.get(f"/api/v1/rfqs/{rfq}/comparison", headers=h).json()["data"]}
    assert comp[hi]["status"] == "rejected" and comp[lo]["status"] == "awarded"
    assert comp[hi]["lineCount"] == 1 and comp[lo]["lineCount"] == 1
    assert comp[hi]["supplierName"] == "Pricy Metals"


def test_sourcing_tenant_isolation_and_money_guards(client):
    c, pem = client
    s = _supplier(c, pem, "ta", "SUP-1", "Solo")
    r = c.post("/api/v1/rfqs", json={"code": "RFQ-9", "title": "Secret buy", "currency": "INR",
                                      "lines": [{"description": "Secret widget", "quantity": 1}]}, headers=_h(pem, "ta"))
    rfq = r.json()["data"]["id"]
    assert c.get(f"/api/v1/rfqs/{rfq}", headers=_h(pem, "tb")).status_code == 404
    c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "sent"}, headers=_h(pem, "ta"))
    (l1,) = rfq_line_ids(c, _h(pem, "ta"), rfq)
    # zero price rejected (no free-money lines in spend analytics)
    bad = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": s, "lines": [{"rfq_line_id": l1, "unit_price_minor": 0, "quantity": 5}]}, headers=_h(pem, "ta"))
    assert bad.status_code == 422
    # unknown supplier rejected
    bad2 = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": "nope", "lines": [{"rfq_line_id": l1, "unit_price_minor": 100, "quantity": 1}]}, headers=_h(pem, "ta"))
    assert bad2.status_code == 422
