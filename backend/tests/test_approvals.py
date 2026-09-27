"""Approvals queue, tier ordering, and referential validation.

Three regressions are covered here:

1. `approvals` was write-only. Nothing could list it, so a submitted
   requisition's approvals could never be decided and the requisition could
   never leave `submitted`.
2. `approve_po` read `pend[0]` off an unordered result, so a finance approver
   could consume the manager's tier and skip a step.
3. `*_id` columns carry no FOREIGN KEY, so the routers now validate the parent
   themselves. A dangling id used to be stored silently.
4. A quote line with no `rfq_line_id` was accepted and then vanished from the
   coverage check that decides whether a bid prices the whole RFQ, so an
   incomplete bid could be evaluated and awarded (VNT-020).
"""
from datetime import datetime, timedelta, timezone

from .helpers import REVIEWER_ROLES, qualified_supplier, rfq_line_ids

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from .helpers import make_category

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
    jwk["kid"] = "ap-kid"
    from app.core import security

    security.override_jwks({"ap-kid": RSAAlgorithm.from_jwk(jwk)})
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
                     pem, algorithm="RS256", headers={"kid": "ap-kid"})
    return {"Authorization": f"Bearer {tok}"}


def _supplier(c, pem, h, code="SUP-1"):
    return c.post("/api/v1/suppliers", json={"code": code, "name": "Acme Parts"}, headers=h).json()["data"]["id"]


def test_approval_queue_is_readable_and_role_gated(client):
    """The read side of the HITL loop: list what is waiting, approvers only."""
    c, pem = client
    h = _h(pem)
    s = _supplier(c, pem, h)
    po = c.post("/api/v1/purchase-orders", json={"code": "PO-Q1", "supplier_id": s, "currency": "USD",
              "lines": [{"description": "Widget", "quantity": 2, "unit_price_minor": 5000}]}, headers=h).json()["data"]["id"]

    # A plain buyer must not be able to read the approval queue.
    assert c.get("/api/v1/approvals", headers=_h(pem, sub="nobody", roles=("Buyer",))).status_code == 403

    q = c.get("/api/v1/approvals", headers=_h(pem, sub="ap1", roles=("Approver",)))
    assert q.status_code == 200
    rows = q.json()["data"]
    assert [r["resourceId"] for r in rows] == [po]
    assert rows[0]["resource"] == "purchase_order"
    assert rows[0]["status"] == "requested"
    assert rows[0]["tier"] == "manager"
    assert rows[0]["requiresHumanReview"] is True
    # filtering by resource and status both work
    assert c.get("/api/v1/approvals?resource=invoice", headers=_h(pem, sub="ap1", roles=("Approver",))).json()["data"] == []
    assert c.get("/api/v1/approvals?status=approved", headers=_h(pem, sub="ap1", roles=("Approver",))).json()["data"] == []
    # tenant isolation on the queue
    assert c.get("/api/v1/approvals", headers=_h(pem, sub="ap1", tenant="other", roles=("Approver",))).json()["data"] == []


def test_requisition_approvals_are_decidable(client):
    """The dead-end: a submitted requisition had approvals nothing could decide."""
    c, pem = client
    h = _h(pem)
    rid = c.post("/api/v1/requisitions", json={"code": "REQ-1", "title": "Fasteners",
                  "lines": [{"description": "Bolt", "quantity": 10, "est_price_minor": 5000}]}, headers=h).json()["data"]["id"]
    assert c.post(f"/api/v1/requisitions/{rid}/submit", headers=h).status_code == 200
    assert c.get("/api/v1/requisitions", headers=h).json()["data"][0]["status"] == "submitted"

    ap = _h(pem, sub="ap1", roles=("Approver",))
    pending = [a for a in c.get("/api/v1/approvals?resource=requisition", headers=ap).json()["data"]
               if a["resourceId"] == rid]
    assert pending, "a submitted requisition must file approvals"
    assert pending[0]["status"] == "requested"

    decided = c.post(f"/api/v1/approvals/{pending[0]['id']}/decide",
                     json={"approve": True, "reason": "budget confirmed"}, headers=ap)
    assert decided.status_code == 200, decided.text
    body = decided.json()["data"]
    assert body["status"] == "approved"
    assert body["resourceStatus"] == "approved"
    # the requisition itself is now approved, not stuck on submitted
    assert c.get("/api/v1/requisitions", headers=h).json()["data"][0]["status"] == "approved"


def test_decide_enforces_sod_role_and_reason(client):
    c, pem = client
    h = _h(pem)
    s = _supplier(c, pem, h)
    rid = c.post("/api/v1/requisitions", json={"code": "REQ-2", "title": "Cables",
                  "lines": [{"description": "Wire", "quantity": 1, "est_price_minor": 1000}]}, headers=h).json()["data"]["id"]
    c.post(f"/api/v1/requisitions/{rid}/submit", headers=h)
    aid = [a for a in c.get("/api/v1/approvals?resource=requisition", headers=h if False else _h(pem, sub="ap1", roles=("Approver",))).json()["data"]
           if a["resourceId"] == rid][0]["id"]

    # the person who raised it cannot clear it (segregation of duties)
    assert c.post(f"/api/v1/approvals/{aid}/decide", json={"approve": True}, headers=h).status_code == 403
    # a buyer is not an approver
    assert c.post(f"/api/v1/approvals/{aid}/decide", json={"approve": True},
                  headers=_h(pem, sub="b2", roles=("Buyer",))).status_code == 403
    ap = _h(pem, sub="ap1", roles=("Approver",))
    # a rejection must say why
    assert c.post(f"/api/v1/approvals/{aid}/decide", json={"approve": False}, headers=ap).status_code == 422
    # re-deciding is a conflict, not a validation error
    assert c.post(f"/api/v1/approvals/{aid}/decide", json={"approve": True, "reason": "ok"}, headers=ap).status_code == 200
    assert c.post(f"/api/v1/approvals/{aid}/decide", json={"approve": True, "reason": "ok"}, headers=ap).status_code == 409
    # a rejection pushes the parent back to rejected
    rid2 = c.post("/api/v1/requisitions", json={"code": "REQ-3", "title": "Gaskets",
                   "lines": [{"description": "Gasket", "quantity": 1, "est_price_minor": 900}]}, headers=h).json()["data"]["id"]
    c.post(f"/api/v1/requisitions/{rid2}/submit", headers=h)
    aid2 = [a for a in c.get("/api/v1/approvals?resource=requisition", headers=ap).json()["data"]
            if a["resourceId"] == rid2][0]["id"]
    r = c.post(f"/api/v1/approvals/{aid2}/decide", json={"approve": False, "reason": "no budget"}, headers=ap)
    assert r.json()["data"]["resourceStatus"] == "rejected"
    assert c.get("/api/v1/requisitions", headers=h).json()["data"][0]["status"] == "rejected"
    assert s


def test_ai_approvals_are_not_decidable_through_the_purchase_route(client):
    """`ai:*` must go through the copilot's own HITL path, not the generic one."""
    c, pem = client
    h = _h(pem)
    filed = c.post("/api/v1/ai/tools/request_approval",
                   json={"action": "award_contract", "resource": "rfq", "resource_id": "rfq-9"},
                   headers=h).json()["data"]["result"]
    aid = filed["approval_id"]
    r = c.post(f"/api/v1/approvals/{aid}/decide", json={"approve": True, "reason": "x"},
               headers=_h(pem, sub="ap1", roles=("Approver",)))
    assert r.status_code == 422
    assert "ai/approvals" in r.json()["error"]["message"]


def test_tiers_are_cleared_in_order_not_row_order(client):
    """A >limit PO needs manager then finance; the manager slot must go first.

    `approve_po` used to take `pend[0]` from an unordered result, so whichever
    row the database returned first could be consumed by any approver.
    """
    c, pem = client
    h = _h(pem)
    s = _supplier(c, pem, h)
    # 250_000 minor > MANAGER_LIMIT_MINOR (100_000) => manager + finance
    po = c.post("/api/v1/purchase-orders", json={"code": "PO-T1", "supplier_id": s, "currency": "USD",
              "lines": [{"description": "Widget", "quantity": 1, "unit_price_minor": 250_000}]}, headers=h).json()["data"]["id"]
    tiers = {a["tier"] for a in c.get("/api/v1/approvals?resource=purchase_order",
                                      headers=_h(pem, sub="ap1", roles=("Approver",))).json()["data"]
             if a["resourceId"] == po}
    assert tiers == {"manager", "finance"}

    # A finance approver acting first must still clear the *manager* tier.
    fin = _h(pem, sub="fin1", roles=("Finance Reviewer",))
    r = c.post(f"/api/v1/purchase-orders/{po}/approve", headers=fin)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["tier"] == "manager"
    assert r.json()["data"]["pending"] == ["finance"]
    assert r.json()["data"]["status"] == "draft"  # not all tiers cleared yet

    # the second pass clears finance and only then approves the PO
    r2 = c.post(f"/api/v1/purchase-orders/{po}/approve", headers=fin)
    assert r2.json()["data"]["tier"] == "finance"
    assert r2.json()["data"]["status"] == "approved"


def test_dangling_category_ids_are_refused(client):
    """No FOREIGN KEY exists, so a bad `category_id` used to be stored silently."""
    c, pem = client
    h = _h(pem)
    s = _supplier(c, pem, h)
    cat = make_category(c, h, "CAT-OK", "Real Category")

    # suppliers
    ok = c.post("/api/v1/suppliers", json={"code": "S-OK", "name": "Categorised", "category_id": cat}, headers=h)
    assert ok.status_code == 201 and ok.json()["data"]["categoryId"] == cat
    ghost = c.post("/api/v1/suppliers", json={"code": "S-GHOST", "name": "Ghosty", "category_id": "nope"}, headers=h)
    assert ghost.status_code == 422
    assert ghost.json()["error"]["code"] == "UNKNOWN_CATEGORY"

    # rfqs
    assert c.post("/api/v1/rfqs", json={"code": "RFQ-1", "title": "Real RFQ", "category_id": cat,
                  "lines": [{"description": "Bolt", "quantity": 1}]}, headers=h).status_code == 201
    assert c.post("/api/v1/rfqs", json={"code": "RFQ-2", "title": "Ghost RFQ", "category_id": "nope",
                  "lines": [{"description": "Bolt", "quantity": 1}]}, headers=h).status_code == 422

    # catalog items
    assert c.post("/api/v1/catalog/items", json={"code": "IT-1", "name": "Item", "category_id": cat}, headers=h).status_code == 201
    assert c.post("/api/v1/catalog/items", json={"code": "IT-2", "name": "Item", "category_id": "nope"}, headers=h).status_code == 422

    # purchase orders
    assert c.post("/api/v1/purchase-orders", json={"code": "PO-1", "supplier_id": s, "category_id": cat,
                  "lines": [{"description": "Bolt", "quantity": 1, "unit_price_minor": 10}]}, headers=h).status_code == 201
    assert c.post("/api/v1/purchase-orders", json={"code": "PO-2", "supplier_id": s, "category_id": "nope",
                  "lines": [{"description": "Bolt", "quantity": 1, "unit_price_minor": 10}]}, headers=h).status_code == 422

    # "" is still allowed and means "deliberately unlinked"
    assert c.post("/api/v1/purchase-orders", json={"code": "PO-3", "supplier_id": s,
                  "lines": [{"description": "Bolt", "quantity": 1, "unit_price_minor": 10}]}, headers=h).status_code == 201


def test_supplier_patch_revalidates_the_category(client):
    c, pem = client
    h = _h(pem)
    cat = make_category(c, h, "CAT-P", "Patchable")
    sid = c.post("/api/v1/suppliers", json={"code": "S-P", "name": "Patchable"}, headers=h).json()["data"]["id"]
    assert c.patch(f"/api/v1/suppliers/{sid}", json={"category_id": cat}, headers=h).status_code == 200
    assert c.get(f"/api/v1/suppliers/{sid}", headers=h).json()["data"]["categoryId"] == cat
    bad = c.patch(f"/api/v1/suppliers/{sid}", json={"category_id": "nope"}, headers=h)
    assert bad.status_code == 422
    # the failed patch must not have half-applied
    assert c.get(f"/api/v1/suppliers/{sid}", headers=h).json()["data"]["categoryId"] == cat


def test_category_parent_cycles_are_refused(client):
    """`categories.parent_id` is the only self-reference; A->B->A was accepted."""
    c, pem = client
    h = _h(pem)
    a = make_category(c, h, "CAT-A", "Alpha")
    b = make_category(c, h, "CAT-B", "Beta", parent_id=a)
    assert b
    # B -> A is fine (no cycle)
    ok = c.post("/api/v1/catalog/categories", json={"code": "CAT-C", "name": "Gamma", "parent_id": b}, headers=h)
    assert ok.status_code == 201
    # a cycle cannot be created through the API, so drive one in directly
    from app.core.tenant import pinned_session
    from app.models.supplier import Category

    db = pinned_session("t1")
    try:
        row = db.get(Category, a)
        assert row is not None
        grand = db.get(Category, ok.json()["data"]["id"])
        assert grand is not None
        # Force a cycle: A -> C, where C descends from A.
        row.parent_id = grand.id
        db.commit()
    finally:
        db.close()
    # now try to re-parent A onto its own descendant
    cyc = c.post("/api/v1/catalog/categories", json={"code": "CAT-D", "name": "Delta", "parent_id": a}, headers=h)
    assert cyc.status_code == 422
    assert cyc.json()["error"]["code"] in {"REFERENCE_CYCLE", "REFERENCE_TOO_DEEP"}
    # an unknown parent is still a plain 422
    assert c.post("/api/v1/catalog/categories", json={"code": "CAT-E", "name": "Epsilon", "parent_id": "nope"}, headers=h).status_code == 422


def test_certification_document_must_exist(client):
    """A certification is evidence; a phantom document_id qualified nobody."""
    c, pem = client
    h = _h(pem)
    sid = _supplier(c, pem, h, "SUP-CERT")
    ghost = c.post(f"/api/v1/suppliers/{sid}/certifications",
                   json={"name": "ISO 9001", "document_id": "no-such-doc"}, headers=h)
    assert ghost.status_code == 422
    assert ghost.json()["error"]["code"] == "UNKNOWN_DOCUMENT"
    # no document_id at all is still allowed (manual evidence)
    assert c.post(f"/api/v1/suppliers/{sid}/certifications", json={"name": "ISO 9001"}, headers=h).status_code == 201


def test_quote_and_invoice_lines_must_belong_to_their_parent(client):
    c, pem = client
    h = _h(pem)
    # A qualified supplier, so the assertions below are about line mapping and
    # currency rather than tripping the eligibility gate first (VNT-020).
    sup = qualified_supplier(c, h, "SUP-Q", "Acme Parts",
                             reviewer_h=_h(pem, sub="reviewer1", roles=REVIEWER_ROLES))
    rfq = c.post("/api/v1/rfqs", json={"code": "RFQ-Q", "title": "Quote test", "currency": "USD",
                "lines": [{"description": "Bolt", "quantity": 10}]}, headers=h).json()["data"]["id"]
    c.patch(f"/api/v1/rfqs/{rfq}/status", json={"status": "sent"}, headers=h)
    (line_id,) = rfq_line_ids(c, h, rfq)
    bad = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": sup, "currency": "USD",
                 "lines": [{"rfq_line_id": "not-a-line", "quantity": 1, "unit_price_minor": 100}]}, headers=h)
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "QUOTE_LINE_NOT_ON_RFQ"

    # VNT-020/VNT-021. An empty rfq_line_id used to be *accepted* and the quote
    # then disappeared from the coverage check that decides whether a bid prices
    # the whole RFQ — so an incomplete bid could be evaluated and awarded. The
    # field is now required, and the currency must be the RFQ's.
    unmapped = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": sup, "currency": "USD",
                      "lines": [{"rfq_line_id": "", "quantity": 1, "unit_price_minor": 100}]}, headers=h)
    assert unmapped.status_code == 422
    assert unmapped.json()["error"]["code"] == "QUOTE_LINE_NOT_ON_RFQ"
    wrong_ccy = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": sup, "currency": "INR",
                      "lines": [{"rfq_line_id": line_id, "quantity": 1, "unit_price_minor": 100}]}, headers=h)
    assert wrong_ccy.status_code == 422
    assert wrong_ccy.json()["error"]["code"] == "QUOTE_CURRENCY_MISMATCH"

    ok = c.post(f"/api/v1/rfqs/{rfq}/quotes", json={"supplier_id": sup, "currency": "USD",
                "lines": [{"rfq_line_id": line_id, "quantity": 1, "unit_price_minor": 100}]}, headers=h)
    assert ok.status_code == 201

    # invoice line must reference a line of *this* PO
    po = c.post("/api/v1/purchase-orders", json={"code": "PO-Q", "supplier_id": sup, "currency": "USD",
              "lines": [{"description": "Bolt", "quantity": 10, "unit_price_minor": 100}]}, headers=h).json()["data"]["id"]
    bad_inv = c.post(f"/api/v1/purchase-orders/{po}/invoices", json={"code": "INV-Q",
                     "lines": [{"po_line_id": "not-a-po-line", "quantity": 1, "unit_price_minor": 100}]}, headers=h)
    assert bad_inv.status_code == 422
    assert bad_inv.json()["error"]["code"] == "INVOICE_LINE_NOT_ON_PO"
