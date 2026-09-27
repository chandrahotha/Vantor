"""Onboarding tests — certs, evidence-gated submit, SoD decide, activation."""
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
    jwk["kid"] = "ob-kid"
    from app.core import security

    security.override_jwks({"ob-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="supplier-side", tenant="t1", roles=("Supplier Manager",)):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "ob-kid"})
    return {"Authorization": f"Bearer {tok}"}


#: The buyer's compliance side. VNT-025/026 made verification and the
#: qualification decision capabilities distinct from supplier editing, and both
#: refuse the submitter — so the happy path now needs two identities, which is
#: what actually happens in a real onboarding.
SUPPLIER_SIDE = ("Supplier Manager",)
COMPLIANCE_SIDE = ("Compliance Reviewer",)


def test_full_onboarding_flow(client):
    c, pem = client
    h = _h(pem)                                  # supplier side
    comp = _h(pem, sub="compliance1", roles=COMPLIANCE_SIDE)
    sid = c.post("/api/v1/suppliers", json={"code": "SUP-OB", "name": "Onboard Me"}, headers=h).json()["data"]["id"]
    # submit with no evidence => submitted (not under_review)
    assert c.post(f"/api/v1/suppliers/{sid}/qualification/submit", headers=h).json()["data"]["status"] == "submitted"
    # decide blocked before review
    assert c.post(f"/api/v1/suppliers/{sid}/qualification/decide", json={"decision": "qualified"}, headers=comp).status_code == 422
    # add cert, verified by the compliance side, then add a B scorecard
    cert = c.post(f"/api/v1/suppliers/{sid}/certifications", json={"name": "ISO 9001", "issuer": "BSI", "valid_until": "2027-01-01"}, headers=h).json()["data"]["id"]
    assert c.post(f"/api/v1/suppliers/{sid}/certifications/{cert}/verify", headers=comp).status_code == 200
    dims = {"quality": 700, "delivery": 700, "price": 700, "compliance": 700, "responsiveness": 700}
    assert c.post(f"/api/v1/suppliers/{sid}/scorecard", json={"dims": dims}, headers=h).json()["data"]["grade"] == "B"
    # rejected case resubmits: first decide path needs under_review — resubmit now auto-advances
    # (previous submit row is in submitted; resubmit blocked? submitted not in draft/rejected => 422, so decide flow uses fresh supplier)
    sid2 = c.post("/api/v1/suppliers", json={"code": "SUP-OB2", "name": "Onboard Two"}, headers=h).json()["data"]["id"]
    c.post(f"/api/v1/suppliers/{sid2}/certifications", json={"name": "ISO 14001"}, headers=h)
    certs = c.get(f"/api/v1/suppliers/{sid2}/certifications", headers=h).json()["data"]
    c.post(f"/api/v1/suppliers/{sid2}/certifications/{certs[0]['id']}/verify", headers=comp)
    c.post(f"/api/v1/suppliers/{sid2}/scorecard", json={"dims": dims}, headers=h)
    st = c.post(f"/api/v1/suppliers/{sid2}/qualification/submit", headers=h).json()["data"]["status"]
    assert st == "under_review"
    # submitter cannot decide own case
    assert c.post(f"/api/v1/suppliers/{sid2}/qualification/decide", json={"decision": "qualified"}, headers=h).status_code == 403
    mgr = _h(pem, sub="mgr1", roles=COMPLIANCE_SIDE)
    assert c.post(f"/api/v1/suppliers/{sid2}/qualification/decide", json={"decision": "qualified", "reason": "evidence complete"}, headers=mgr).json()["data"]["status"] == "qualified"
    # qualified draft supplier becomes active
    assert c.get(f"/api/v1/suppliers/{sid2}", headers=h).json()["data"]["status"] == "active"
    assert c.get(f"/api/v1/suppliers/{sid2}/qualification", headers=_h(pem, tenant="other")).status_code == 404


def test_supplier_side_cannot_verify_or_qualify(client):
    """VNT-025/026: the supplier-side roles must not be the deciding authority.

    Before this, a `Supplier Manager` could verify their own certifications and
    qualify their own employer, and the only thing standing in the way was a
    `created_by` comparison that this same test had to be careful about.
    """
    c, pem = client
    supplier = _h(pem, sub="supplier-side", roles=SUPPLIER_SIDE)
    sid = c.post("/api/v1/suppliers", json={"code": "SUP-SOD", "name": "Sod Ltd"},
                 headers=supplier).json()["data"]["id"]
    cert = c.post(f"/api/v1/suppliers/{sid}/certifications", json={"name": "ISO 9001", "issuer": "BSI"},
                  headers=supplier).json()["data"]["id"]
    # Not 403-for-SoD: 403 because the *role* is wrong, before we even get to
    # asking who submitted it.
    refused = c.post(f"/api/v1/suppliers/{sid}/certifications/{cert}/verify", headers=supplier)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "SUPPLIER_ACTION_FORBIDDEN"
    assert refused.json()["error"]["details"]["action"] == "verify_cert"

    # A Buyer is no better: editing rights are not verification rights.
    buyer = _h(pem, sub="buyer1", roles=("Buyer",))
    assert c.post(f"/api/v1/suppliers/{sid}/certifications/{cert}/verify", headers=buyer).status_code == 403


def test_certification_cannot_be_verified_after_expiry(client):
    """VNT-025: `valid_until` existed and was never compared to anything."""
    c, pem = client
    supplier = _h(pem, sub="supplier-side", roles=SUPPLIER_SIDE)
    comp = _h(pem, sub="compliance1", roles=COMPLIANCE_SIDE)
    sid = c.post("/api/v1/suppliers", json={"code": "SUP-EXP", "name": "Expired Ltd"},
                 headers=supplier).json()["data"]["id"]
    cert = c.post(f"/api/v1/suppliers/{sid}/certifications",
                  json={"name": "ISO 9001", "issuer": "BSI", "valid_until": "2000-01-01"},
                  headers=supplier).json()["data"]["id"]
    res = c.post(f"/api/v1/suppliers/{sid}/certifications/{cert}/verify", headers=comp)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "CERT_EXPIRED"
    assert res.json()["error"]["details"]["validUntil"] == "2000-01-01"


def test_qualification_rejection_requires_a_reason(client):
    """VNT-026: `reason` defaulted to empty and nothing rejected the empty case."""
    c, pem = client
    supplier = _h(pem, sub="supplier-side", roles=SUPPLIER_SIDE)
    comp = _h(pem, sub="compliance1", roles=COMPLIANCE_SIDE)
    dims = {"quality": 700, "delivery": 700, "price": 700, "compliance": 700, "responsiveness": 700}
    sid = c.post("/api/v1/suppliers", json={"code": "SUP-REJ", "name": "Reject Ltd"},
                 headers=supplier).json()["data"]["id"]
    cert = c.post(f"/api/v1/suppliers/{sid}/certifications", json={"name": "ISO 9001", "issuer": "BSI"},
                  headers=supplier).json()["data"]["id"]
    c.post(f"/api/v1/suppliers/{sid}/certifications/{cert}/verify", headers=comp)
    c.post(f"/api/v1/suppliers/{sid}/scorecard", json={"dims": dims}, headers=supplier)
    c.post(f"/api/v1/suppliers/{sid}/qualification/submit", headers=supplier)

    bare = c.post(f"/api/v1/suppliers/{sid}/qualification/decide",
                  json={"decision": "rejected"}, headers=comp)
    assert bare.status_code == 422
    assert bare.json()["error"]["code"] == "REASON_REQUIRED"

    ok = c.post(f"/api/v1/suppliers/{sid}/qualification/decide",
                json={"decision": "rejected", "reason": "certificate is for a different entity"},
                headers=comp)
    assert ok.status_code == 200
    assert ok.json()["data"]["status"] == "rejected"


def test_qualification_decision_refreezes_evidence(client):
    """The >=1 verified cert + grade gate is re-checked at decision time.

    A certification can be quarantined or withdrawn between submission and
    decision, and a qualified supplier is one that can bid.
    """
    c, pem = client
    supplier = _h(pem, sub="supplier-side", roles=SUPPLIER_SIDE)
    comp = _h(pem, sub="compliance1", roles=COMPLIANCE_SIDE)
    dims = {"quality": 900, "delivery": 900, "price": 900, "compliance": 900, "responsiveness": 900}
    sid = c.post("/api/v1/suppliers", json={"code": "SUP-FRZ", "name": "Freeze Ltd"},
                 headers=supplier).json()["data"]["id"]
    cert = c.post(f"/api/v1/suppliers/{sid}/certifications", json={"name": "ISO 9001", "issuer": "BSI"},
                  headers=supplier).json()["data"]["id"]
    c.post(f"/api/v1/suppliers/{sid}/certifications/{cert}/verify", headers=comp)
    c.post(f"/api/v1/suppliers/{sid}/scorecard", json={"dims": dims}, headers=supplier)
    c.post(f"/api/v1/suppliers/{sid}/qualification/submit", headers=supplier)

    # Withdraw the evidence after submission.
    from app.core.tenant import pinned_session
    from app.models.onboarding import SupplierCertification

    db = pinned_session("t1")
    try:
        row = db.query(SupplierCertification).filter(SupplierCertification.id == cert).one()
        row.status = "rejected"
        db.commit()
    finally:
        db.close()

    res = c.post(f"/api/v1/suppliers/{sid}/qualification/decide",
                 json={"decision": "qualified", "reason": "looks fine"}, headers=comp)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "NO_CURRENT_EVIDENCE"
