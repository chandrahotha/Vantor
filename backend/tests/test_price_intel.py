"""Price intel tests — median baselines, thin-history refusal, anomaly cases."""
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
    jwk["kid"] = "pi-kid"
    from app.core import security

    security.override_jwks({"pi-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="buyer1", tenant="t1", roles=("Buyer",)):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "pi-kid"})
    return {"Authorization": f"Bearer {tok}"}


def _full_p2p(c, pem, tenant, sub, code, price, qty=10, supplier_id=None):
    """Create supplier→PO→approve→send→receive→invoice→approve. Returns (po_id, inv_id)."""
    h = _h(pem, sub, tenant)
    if supplier_id is None:
        supplier_id = c.post("/api/v1/suppliers", json={"code": f"S-{code}", "name": f"Sup {code}"}, headers=h).json()["data"]["id"]
    s = supplier_id
    po = c.post("/api/v1/purchase-orders", json={"code": f"PO-{code}", "supplier_id": s,
                "lines": [{"description": "Bolt M10", "quantity": qty, "unit_price_minor": price}]}, headers=h).json()["data"]["id"]
    now = datetime.now(timezone.utc)
    import jwt as _jwt

    mtok = _jwt.encode({"iss": ISS, "aud": AUD, "sub": "mgr-" + sub, "tenant_id": tenant,
                        "realm_access": {"roles": ["Procurement Manager"]},
                        "exp": now + timedelta(minutes=5), "iat": now}, pem, algorithm="RS256", headers={"kid": "pi-kid"})
    mh = {"Authorization": f"Bearer {mtok}"}
    assert c.post(f"/api/v1/purchase-orders/{po}/approve", headers=mh).status_code == 200
    assert c.post(f"/api/v1/purchase-orders/{po}/send", headers=h).status_code == 200
    pod = c.get(f"/api/v1/purchase-orders/{po}", headers=h).json()["data"]
    plid = pod["lines"][0]["id"]
    assert c.post(f"/api/v1/purchase-orders/{po}/receipts", json={"notes": "ok", "lines": [{"po_line_id": plid, "quantity": qty}]}, headers=h).status_code == 201
    inv = c.post(f"/api/v1/purchase-orders/{po}/invoices", json={"code": f"INV-{code}",
                "lines": [{"po_line_id": plid, "quantity": qty, "unit_price_minor": price}]}, headers=h).json()["data"]["id"]
    assert c.post(f"/api/v1/invoices/{inv}/approve", headers=mh).status_code == 200
    return po, inv


def test_baseline_and_anomaly_flow(client):
    from app.services.price_intel import normalize_item, variance_bp

    assert normalize_item("  Bolt   M10 ") == "bolt m10"
    c, pem = client
    # one supplier, 3 history POs @500, 520, 510 => median 510; 4th @800 => +56.9% anomaly
    sup = c.post("/api/v1/suppliers", json={"code": "S-HIST", "name": "History Parts"}, headers=_h(pem, "u0", "acme")).json()["data"]["id"]
    for i, price in enumerate([500, 520, 510]):
        _full_p2p(c, pem, "acme", f"u{i}", f"H{i}", price, supplier_id=sup)
    _full_p2p(c, pem, "acme", "u9", "SPIKE", 800, supplier_id=sup)
    pos = c.get("/api/v1/purchase-orders", headers=_h(pem, "u0", "acme")).json()["data"]
    spike = [p for p in pos if p["code"] == "PO-SPIKE"][0]
    ev = c.post(f"/api/v1/spend/price-evaluate/{spike['id']}", headers=_h(pem, "u0", "acme"))
    assert ev.status_code == 201, ev.text
    assert len(ev.json()["data"]["opened"]) == 1
    cases = c.get("/api/v1/spend/price-cases?status=open", headers=_h(pem, "u0", "acme")).json()["data"]
    assert len(cases) == 1
    assert cases[0]["baselineMinor"] == 510 and cases[0]["quotedMinor"] == 800
    assert cases[0]["varianceBp"] == variance_bp(baseline_minor=510, quoted_minor=800) == 5686
    assert cases[0]["samples"] == 3
    cid = cases[0]["id"]
    # Resolving a case RETIRES the control that flagged it, so it is narrower
    # than opening one: the buyer who raised the over-priced PO must not be able
    # to dismiss the anomaly raised against it. This router had no role set at
    # all, so this was previously reachable by any member of the tenant.
    buyer = _h(pem, "u0", "acme")
    assert c.post(f"/api/v1/spend/price-cases/{cid}/resolve",
                  json={"status": "bogus"}, headers=buyer).status_code == 403
    finance = _h(pem, "fin1", "acme", roles=("Finance Reviewer",))
    assert c.post(f"/api/v1/spend/price-cases/{cid}/resolve",
                  json={"status": "bogus"}, headers=finance).status_code == 422
    assert c.post(f"/api/v1/spend/price-cases/{cid}/resolve",
                  json={"status": "handed_off"}, headers=finance).json()["data"]["status"] == "handed_off"
    assert c.get("/api/v1/spend/price-cases?status=open", headers=finance).json()["data"] == []
    # a Read Only seat cannot evaluate either — evaluation writes case rows
    readonly = _h(pem, "ro1", "acme", roles=("Read Only",))
    assert c.post(f"/api/v1/spend/price-evaluate/{spike['id']}", headers=readonly).status_code == 403
    # other tenant isolated
    assert c.get("/api/v1/spend/price-cases", headers=_h(pem, "u0", "other")).json()["data"] == []


def test_thin_history_skipped_not_flagged(client):
    c, pem = client
    po, _ = _full_p2p(c, pem, "solo", "u1", "ONLY", 100)
    ev = c.post(f"/api/v1/spend/price-evaluate/{po}", headers=_h(pem, "u1", "solo")).json()["data"]
    assert ev["opened"] == [] and len(ev["skipped"]) == 1
    assert ev["skipped"][0]["reason"] in {"PRICE_NO_HISTORY", "PRICE_THIN_HISTORY"}


def test_the_database_refuses_a_second_open_case_for_one_line(client):
    """Migration 0030's invariant, asserted where it is actually enforced.

    `POST /spend/price-evaluate/{po}` reads the open cases for a PO and then
    inserts one per anomalous line. Two concurrent evaluations both read "none
    open for line 3" and both inserted — the endpoint's batch shape cannot be
    made safe by choosing to look before writing, so the arbitration belongs in
    a unique index. This test is the index, not the handler: a handler test could
    pass while the constraint was dropped.
    """
    from sqlalchemy.exc import IntegrityError

    from app.core.tenant import pinned_session
    from app.models.pricecase import PriceCase

    c, pem = client
    sup = c.post("/api/v1/suppliers", json={"code": "S-DUP", "name": "Dup Parts"},
                 headers=_h(pem, "u0", "acme")).json()["data"]["id"]
    _full_p2p(c, pem, "acme", "u1", "DUP1", 700, supplier_id=sup)
    pos = c.get("/api/v1/purchase-orders", headers=_h(pem, "u0", "acme")).json()["data"]
    po = pos[0]
    line_id = c.get(f"/api/v1/purchase-orders/{po['id']}", headers=_h(pem, "u0", "acme")).json()["data"]["lines"][0]["id"]

    db = pinned_session("acme")
    try:
        def open_case(who: str) -> PriceCase:
            return PriceCase(tenant_id="acme", created_by=who, updated_by=who,
                             po_id=po["id"], po_line_id=line_id, supplier_id=sup,
                             item="bolt m10", baseline_minor=500, quoted_minor=900,
                             variance_bp=8000, samples=3, status="open", detail={})

        db.add(open_case("first"))
        db.flush()
        db.add(open_case("second"))
        try:
            db.flush()
            raised = False
        except IntegrityError:
            raised = True
        assert raised, (
            "a second OPEN case for the same (tenant, po_line_id) was accepted — "
            "the duplicate-open race is unguarded again")
        db.rollback()

        # The predicate's `po_line_id <> ''` half: cases raised without a specific
        # line are legitimate in number, and a predicate that forgot the clause
        # would let the first one block every later one in the tenant.
        for i in range(3):
            db.add(PriceCase(tenant_id="acme", created_by=f"nolink{i}", updated_by=f"nolink{i}",
                             po_id=po["id"], po_line_id="", supplier_id=sup,
                             item="unattached", baseline_minor=500, quoted_minor=900,
                             variance_bp=8000, samples=0, status="open", detail={}))
        db.flush()

        # Closed cases must not occupy the slot, or re-evaluation after a review
        # could never open a fresh case for the same line.
        db.add(PriceCase(tenant_id="acme", created_by="again", updated_by="again",
                         po_id=po["id"], po_line_id=line_id, supplier_id=sup,
                         item="bolt m10", baseline_minor=500, quoted_minor=900,
                         variance_bp=8000, samples=3, status="dismissed", detail={}))
        db.flush()
        db.commit()
    finally:
        db.close()


def test_re_evaluating_a_po_reports_the_existing_case_rather_than_duplicating(client):
    """The handler's own answer when the line is already open."""
    c, pem = client
    sup = c.post("/api/v1/suppliers", json={"code": "S-TWICE", "name": "Twice Parts"},
                 headers=_h(pem, "u0", "acme")).json()["data"]["id"]
    for i, price in enumerate([500, 520, 510]):
        _full_p2p(c, pem, "acme", f"u{i}", f"T{i}", price, supplier_id=sup)
    _full_p2p(c, pem, "acme", "u9", "T9", 800, supplier_id=sup)
    pos = c.get("/api/v1/purchase-orders", headers=_h(pem, "u0", "acme")).json()["data"]
    spike = [p for p in pos if p["code"] == "PO-T9"][0]

    first = c.post(f"/api/v1/spend/price-evaluate/{spike['id']}", headers=_h(pem, "u0", "acme"))
    assert first.status_code == 201, first.text
    assert len(first.json()["data"]["opened"]) == 1

    again = c.post(f"/api/v1/spend/price-evaluate/{spike['id']}", headers=_h(pem, "u0", "acme"))
    assert again.json()["data"]["opened"] == [], again.text
    assert again.json()["data"]["skipped"][0]["reason"] == "PRICE_CASE_OPEN"
    cases = c.get("/api/v1/spend/price-cases?status=open", headers=_h(pem, "u0", "acme")).json()["data"]
    assert len(cases) == 1, [c["id"] for c in cases]
