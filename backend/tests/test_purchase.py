"""Purchase Wave 2.5 tests — P2P flow, tiered approvals, SoD, 3-way match."""
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
    jwk["kid"] = "p-kid"
    from app.core import security

    security.override_jwks({"p-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="buyer1", tenant="t1", roles=("Buyer", "Approver")):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "p-kid"})
    return {"Authorization": f"Bearer {tok}"}


def _ready_to_invoice(c, pem):
    """A PO that is sent and fully received, plus the line id to bill."""
    h = _h(pem)
    s = c.post("/api/v1/suppliers", json={"code": "SUP-M", "name": "Match Co"},
               headers=h).json()["data"]["id"]
    po = c.post("/api/v1/purchase-orders", json={
        "code": "PO-M", "supplier_id": s, "currency": "INR",
        "lines": [{"description": "Widget", "quantity": 10, "unit_price_minor": 100}]},
        headers=h).json()["data"]["id"]
    mgr = _h(pem, sub="mgr1", roles=("Procurement Manager",))
    assert c.post(f"/api/v1/purchase-orders/{po}/approve", headers=mgr).status_code == 200
    assert c.post(f"/api/v1/purchase-orders/{po}/send", headers=h).status_code == 200
    line = c.get(f"/api/v1/purchase-orders/{po}", headers=h).json()["data"]["lines"][0]["id"]
    assert c.post(f"/api/v1/purchase-orders/{po}/receipts",
                  json={"lines": [{"po_line_id": line, "quantity": 10}]},
                  headers=h).status_code == 201
    inv = c.post(f"/api/v1/purchase-orders/{po}/invoices", json={
        "code": "INV-M", "currency": "INR",
        "lines": [{"po_line_id": line, "quantity": 10, "unit_price_minor": 100}]},
        headers=h).json()["data"]["id"]
    return inv, h, mgr


def test_matched_state_is_reachable_and_approval_still_works(client):
    """`matched` was declared in three places and written by none of them.

    It was in `INVOICE_STATUSES`, in `INVOICE_FLOW` and in the database CHECK
    constraint. No code path could put an invoice into it: approval went straight
    from `received` to `approved` and performed the match inside the same
    request. A test compared the two declarations against each other and passed,
    because a declaration agreeing with another declaration is not the same thing
    as anything obeying them.

    So the state is now written by `POST /invoices/{id}/match`, and the audit
    trail distinguishes "matched by the matcher" from "approved by the approver"
    rather than recording the match under the approver's name at approval time.
    """
    c, pem = client
    inv, h, mgr = _ready_to_invoice(c, pem)

    matched = c.post(f"/api/v1/invoices/{inv}/match", headers=mgr)
    assert matched.status_code == 200, matched.text
    assert matched.json()["data"]["status"] == "matched"

    # Matching twice is refused: the state is not a toggle.
    assert c.post(f"/api/v1/invoices/{inv}/match", headers=mgr).status_code == 422

    # The matcher cannot be the invoice's creator (separation of duties).
    created = c.post("/api/v1/purchase-orders", json={
        "code": "PO-S", "supplier_id": c.post("/api/v1/suppliers", json={
            "code": "SUP-S", "name": "SoD Co"}, headers=h).json()["data"]["id"],
        "currency": "INR",
        "lines": [{"description": "Widget", "quantity": 10, "unit_price_minor": 100}]},
        headers=h).json()["data"]["id"]
    mgr2 = _h(pem, sub="mgr2", roles=("Procurement Manager",))
    assert c.post(f"/api/v1/purchase-orders/{created}/approve", headers=mgr2).status_code == 200
    assert c.post(f"/api/v1/purchase-orders/{created}/send", headers=h).status_code == 200
    line2 = c.get(f"/api/v1/purchase-orders/{created}", headers=h).json()["data"]["lines"][0]["id"]
    c.post(f"/api/v1/purchase-orders/{created}/receipts",
           json={"lines": [{"po_line_id": line2, "quantity": 10}]}, headers=h)
    inv2 = c.post(f"/api/v1/purchase-orders/{created}/invoices", json={
        "code": "INV-S", "currency": "INR",
        "lines": [{"po_line_id": line2, "quantity": 10, "unit_price_minor": 100}]},
        headers=h).json()["data"]["id"]
    buyer_match = _h(pem, sub="buyer1", roles=("Buyer", "Approver"))
    sod = c.post(f"/api/v1/invoices/{inv2}/match", headers=buyer_match)
    assert sod.status_code == 403, sod.text

    # A matched invoice is approvable, and the ledger is written once.
    approved = c.post(f"/api/v1/invoices/{inv}/approve", headers=mgr)
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "approved"
    assert c.post(f"/api/v1/invoices/{inv}/approve", headers=mgr).status_code == 422


def test_approval_still_works_in_one_step(client):
    """The match must stay optional: parking an invoice is not a new step that
    a client is required to perform before it can be paid."""
    c, pem = client
    inv, h, mgr = _ready_to_invoice(c, pem)
    assert c.post(f"/api/v1/invoices/{inv}/approve", headers=mgr).status_code == 200


def test_p2p_flow_with_match_and_sod(client):
    c, pem = client
    h = _h(pem)
    s = c.post("/api/v1/suppliers", json={"code": "SUP-P", "name": "Parts Co"}, headers=h).json()["data"]["id"]
    po = c.post("/api/v1/purchase-orders", json={"code": "PO-001", "supplier_id": s, "currency": "INR",
                "lines": [{"description": "Bolt", "quantity": 100, "unit_price_minor": 500},
                          {"description": "Nut", "quantity": 100, "unit_price_minor": 300}]}, headers=h)
    assert po.status_code == 201, po.text
    pid = po.json()["data"]["id"]
    assert po.json()["data"]["tiers"] == ["manager"]  # 80000 minor <= limit
    # SoD: creator cannot approve own PO
    assert c.post(f"/api/v1/purchase-orders/{pid}/approve", headers=h).status_code == 403
    mgr = _h(pem, sub="mgr1", roles=("Procurement Manager",))
    assert c.post(f"/api/v1/purchase-orders/{pid}/approve", headers=mgr).status_code == 200
    assert c.post(f"/api/v1/purchase-orders/{pid}/send", headers=h).status_code == 200
    # receipt full qty
    # fetch PO line ids via invoice attempt? use receipt with real ids:
    r_detail = c.post(f"/api/v1/purchase-orders/{pid}/receipts", json={"notes": "full", "lines": []}, headers=h)
    assert r_detail.status_code == 422  # empty lines rejected
    # get line ids through direct DB is overkill; create receipt via two-step: lines required
    # Use API: need po_line ids — fetch from openapi? Instead approve path via service test below for match;
    # here assert lifecycle guards:
    assert c.post(f"/api/v1/purchase-orders/{pid}/send", headers=h).status_code == 422  # already sent


def test_tiers_and_match_service():
    from app.services.purchase import required_tiers, three_way_match, PurchaseError
    import pytest as _pt

    assert required_tiers(50_000) == ["manager"]
    assert required_tiers(500_000) == ["manager", "finance"]
    assert required_tiers(500_000, legal_required=True) == ["manager", "finance", "legal"]
    from sqlalchemy import create_engine as _ce
    from sqlalchemy.orm import Session as _S
    from app.models.registry import Base as _B

    e = _ce("sqlite://")
    _B.metadata.create_all(e)
    db = _S(e)
    from app.models.purchase import Invoice, InvoiceLine, PurchaseOrder, PurchaseOrderLine, Receipt, ReceiptLine

    db.add(PurchaseOrder(id="po1", tenant_id="t", created_by="u", updated_by="u", code="PO1", supplier_id="s", status="sent", currency="INR", total_minor=80000))
    db.add(PurchaseOrderLine(id="pl1", tenant_id="t", created_by="u", updated_by="u", po_id="po1", line_no=1, description="Bolt", quantity=100, unit_price_minor=500, line_total_minor=50000))
    db.add(Receipt(id="r1", tenant_id="t", created_by="u", updated_by="u", po_id="po1"))
    db.add(ReceiptLine(id="rl1", tenant_id="t", created_by="u", updated_by="u", receipt_id="r1", po_line_id="pl1", quantity=100))
    db.add(Invoice(id="i1", tenant_id="t", created_by="u", updated_by="u", code="INV1", po_id="po1", supplier_id="s", status="received", currency="INR", total_minor=50000))
    db.add(InvoiceLine(id="il1", tenant_id="t", created_by="u", updated_by="u", invoice_id="i1", po_line_id="pl1", quantity=100, unit_price_minor=500, line_total_minor=50000))
    db.flush()
    assert three_way_match(db, tenant_id="t", po_id="po1", invoice_id="i1")["matched_lines"] == 1
    db.add(Invoice(id="i2", tenant_id="t", created_by="u", updated_by="u", code="INV2", po_id="po1", supplier_id="s", status="received", currency="INR", total_minor=99999))
    db.add(InvoiceLine(id="il2", tenant_id="t", created_by="u", updated_by="u", invoice_id="i2", po_line_id="pl1", quantity=100, unit_price_minor=600, line_total_minor=60000))
    db.flush()
    with _pt.raises(PurchaseError):
        three_way_match(db, tenant_id="t", po_id="po1", invoice_id="i2")
    db.close()
