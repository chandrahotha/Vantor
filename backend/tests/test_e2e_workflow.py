"""E2E real-world workflow: one full procurement day across supplier, sourcing,
contract, purchase, spend, and notification layers, then audit-chain verify.

The product claims a graph; this test walks the graph and asserts the joins.

The onboarding order below is not incidental. VNT-020 made supplier eligibility
a real gate: a supplier must be `active` and hold a `qualified` qualification
before it may submit a bid, and VNT-025 made certification verification and the
qualification decision segregation-of-duties controls. So the flow now has to
onboard a supplier before it can source against it, which is the order a real
procurement team works in anyway.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from .helpers import rfq_line_ids

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
    jwk["kid"] = "e2e-kid"
    from app.core import security

    security.override_jwks({"e2e-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="u1", tenant="acme", roles=("Buyer", "Procurement Manager", "Approver")):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "e2e-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_procurement_day_end_to_end(client):
    c, pem = client
    buyer = _h(pem, "buyer1")
    mgr = _h(pem, "mgr1")
    # VNT-025/026: certification verification and the qualification decision are
    # the compliance side's calls, not the buyer's or the procurement manager's.
    comp = _h(pem, "compliance1", roles=("Compliance Reviewer",))

    # 1. Catalog + supplier
    cat = c.post("/api/v1/catalog/categories", json={"code": "CAT-MRO", "name": "MRO"}, headers=buyer).json()["data"]["id"]
    sup = c.post("/api/v1/suppliers", json={"code": "SUP-1", "name": "Acme MRO", "currency": "INR"}, headers=buyer).json()["data"]["id"]

    # onboard: cert + scorecard + qualification forward
    # onboard: verify cert then scorecard, then submit auto-advances the case.
    # VNT-020: the supplier must be `active` and hold a `qualified`
    # qualification before it may bid at all — which is the point of doing
    # onboarding before the RFQ, so the flow below reads in the right order.
    assert c.patch(f"/api/v1/suppliers/{sup}", json={"status": "active"}, headers=buyer).status_code == 200
    cd = c.post(f"/api/v1/suppliers/{sup}/certifications", json={"name": "ISO 9001", "issuer": "BSI", "valid_until": "2027-12-31"}, headers=buyer).json()["data"]["id"]
    assert cd
    assert c.post(f"/api/v1/suppliers/{sup}/certifications/{cd}/verify", headers=comp).status_code == 200
    assert c.post(f"/api/v1/suppliers/{sup}/scorecard", json={"dims": {
        "quality": 900, "delivery": 850, "price": 800, "compliance": 900, "responsiveness": 850}}, headers=buyer).status_code == 201
    assert c.post(f"/api/v1/suppliers/{sup}/qualification/submit", headers=buyer).status_code == 200
    # VNT-026: deciding a qualification needs the compliance role, and a reason.
    decided = c.post(f"/api/v1/suppliers/{sup}/qualification/decide",
                     json={"decision": "qualified", "reason": "evidence complete"}, headers=comp)
    assert decided.status_code == 200, decided.text

    # 2. RFQ with a quote; evaluate + award writes savings. VNT-021: the quote
    # cites the RFQ line and carries the RFQ's currency.
    rfq = c.post("/api/v1/rfqs", json={"code": "RFQ-D", "title": "Fasteners", "currency": "INR",
                 "lines": [{"description": "M10 bolt", "quantity": 100}]}, headers=buyer).json()["data"]["id"]
    (rfq_line,) = rfq_line_ids(c, buyer, rfq)
    c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "sent"}, headers=buyer)
    q1 = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": sup, "currency": "INR",
                "lines": [{"rfq_line_id": rfq_line, "unit_price_minor": 500, "quantity": 100}]}, headers=buyer).json()["data"]["id"]
    c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "response"}, headers=buyer)
    c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "evaluated"}, headers=buyer)
    award = c.post(f"/api/v1/rfqs/{rfq}/award", json={"quote_id": q1, "reason": "cheapest valid bid"}, headers=buyer)
    assert award.status_code == 201

    # 3. Contract for the winning supplier. VNT-022: the buyer drafts it and
    # routes it, but activating and signing are separate authorities — a
    # Procurement Manager can activate, and only Legal can bind the company.
    order = c.post("/api/v1/contracts", json={"code": "CT-D", "title": "MRO supply 2026", "supplier_id": sup,
                "value_minor": 500_000, "currency": "INR", "start_date": "2026-09-01", "end_date": "2027-08-31"}, headers=buyer)
    cid = order.json()["data"]["id"]
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=buyer)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=mgr)
    legal = _h(pem, "legal1", roles=("Legal Reviewer",))
    signed = c.post(f"/api/v1/contracts/{cid}/sign", json={"method": "internal"}, headers=legal)
    assert signed.status_code == 201, signed.text
    # The drafter could not have signed it, whatever their procurement role.
    assert c.post(f"/api/v1/contracts/{cid}/sign", json={"method": "esign", "provider": "docusign",
                                                          "envelope_id": "env-e2e"}, headers=buyer).status_code == 403

    # 4. PO → approve → send → receive → invoice → 3-way match approve
    po = c.post("/api/v1/purchase-orders", json={"code": "PO-D", "supplier_id": sup, "currency": "INR", "category_id": cat,
                "lines": [{"description": "M10 bolt", "quantity": 100, "unit_price_minor": 500}]}, headers=buyer).json()["data"]["id"]
    assert sum(1 for _ in c.get(f"/api/v1/purchase-orders/{po}", headers=buyer).json()["data"]["lines"]) == 1
    line = c.get(f"/api/v1/purchase-orders/{po}", headers=buyer).json()["data"]["lines"][0]["id"]
    # buyer cannot approve own PO
    assert c.post(f"/api/v1/purchase-orders/{po}/approve", headers=buyer).status_code == 403
    assert c.post(f"/api/v1/purchase-orders/{po}/approve", headers=mgr).status_code == 200
    assert c.post(f"/api/v1/purchase-orders/{po}/send", headers=buyer).status_code == 200
    assert c.post(f"/api/v1/purchase-orders/{po}/receipts", json={"lines": [{"po_line_id": line, "quantity": 100}]}, headers=buyer).status_code == 201
    inv = c.post(f"/api/v1/purchase-orders/{po}/invoices", json={"code": "INV-D", "currency": "INR",
                 "lines": [{"po_line_id": line, "quantity": 100, "unit_price_minor": 500}]}, headers=buyer).json()["data"]["id"]
    assert c.post(f"/api/v1/invoices/{inv}/approve", headers=mgr).status_code == 200

    # 5. Spend summary actually picked it up
    spend = c.get("/api/v1/spend/summary", headers=buyer).json()["data"]
    assert spend["currencyCount"] == 1
    assert spend["byCurrency"]["committed"]["INR"] == 50_000
    assert spend["byCurrency"]["invoiced"]["INR"] == 50_000
    assert spend["byCurrency"]["saved"].get("INR", 0) >= 0

    # 6. Notifications landed (award broadcast + PO approval directed)
    unread = c.get("/api/v1/notifications/unread-count", headers=buyer).json()["data"]["unread"]
    assert unread >= 1
    kinds = {n["kind"] for n in c.get("/api/v1/notifications", headers=buyer).json()["data"]}
    assert "AWARD_DECIDED" in kinds

    # 7. Audit chain verifies — no tamper
    v = c.get("/api/v1/audit-events/verify", headers=buyer).json()["data"]
    assert v["valid"] is True

    # 8. Tenant isolation: another namespace sees none of it
    other = _h(pem, "x", "void")
    assert c.get("/api/v1/spend/summary", headers=other).json()["data"]["currencyCount"] == 0
    assert c.get("/api/v1/notifications", headers=other).json()["data"] == []
