"""Requisitions — create → list → submit → tier seeding. Previously the only
uncovered module on the purchase path: no test touched it at all."""
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
    jwk["kid"] = "req-kid"
    from app.core import security

    security.override_jwks({"req-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="req1", tenant="t1", roles=("Buyer", "Procurement Manager")):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "req-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_create_list_and_submit_flow(client):
    c, pem = client
    h = _h(pem)

    # Empty tenant: the list endpoint exists, paginates, and returns nothing.
    empty = c.get("/api/v1/requisitions", headers=h).json()
    assert empty["data"] == [] and empty["pagination"]["hasMore"] is False

    r = c.post("/api/v1/requisitions", json={
        "code": "REQ-101", "title": "Fasteners topup",
        "lines": [
            {"description": "M10 bolt", "quantity": 100, "est_price_minor": 500},
            {"description": "M8 nut", "quantity": 200, "est_price_minor": 350},
        ],
    }, headers=h)
    assert r.status_code == 201, r.text
    rid = r.json()["data"]["id"]

    dup = c.post("/api/v1/requisitions", json={"code": "req-101", "title": "Duplicate code", "lines": []}, headers=h)
    assert dup.status_code == 409

    lst = c.get("/api/v1/requisitions", headers=h).json()["data"]
    assert any(x["code"] == "REQ-101" for x in lst)

    # Submit is idempotent-guarded: a second submit is a 422, not a silent re-run.
    assert c.post(f"/api/v1/requisitions/{rid}/submit", headers=h).status_code == 200
    again = c.post(f"/api/v1/requisitions/{rid}/submit", headers=h)
    assert again.status_code == 422

    # Status filter reflects the transition.
    drafts = c.get("/api/v1/requisitions?status=draft", headers=h).json()["data"]
    assert all(x["code"] != "REQ-101" for x in drafts)
    submitted = c.get("/api/v1/requisitions?status=submitted", headers=h).json()["data"]
    assert any(x["code"] == "REQ-101" for x in submitted)


def test_submit_seeds_at_least_one_approval(client):
    """The submit side effect matters: approvals exist so a human gate stands
    between "requested" and "purchase order". A submit that seeded zero approvals
    would be a silent bypass of segregation of duties."""
    c, pem = client
    h = _h(pem)
    rid = c.post("/api/v1/requisitions", json={
        "code": "REQ-202", "title": "Lab equipment",
        "lines": [{"description": "Centrifuge unit", "quantity": 1, "est_price_minor": 250000}],
    }, headers=h).json()["data"]["id"]
    assert c.post(f"/api/v1/requisitions/{rid}/submit", headers=h).status_code == 200

    from app.core.tenant import pinned_session
    from sqlalchemy import func, select
    from app.models.purchase import Approval

    db = pinned_session("t1")
    try:
        n = db.execute(select(func.count()).select_from(Approval).where(
            Approval.tenant_id == "t1", Approval.resource == "requisition", Approval.resource_id == rid)).scalar()
    finally:
        db.close()
    assert n and n >= 1, "submit must seed at least one approval record"


def test_writes_are_role_gated_and_tenant_scoped(client):
    c, pem = client
    ro = _h(pem, "readonly", "t1", roles=("Read Only",))
    assert c.post("/api/v1/requisitions", json={"code": "REQ-9", "title": "Nope", "lines": []}, headers=ro).status_code == 403

    h = _h(pem, "u1", "t1")
    c.post("/api/v1/requisitions", json={"code": "REQ-1", "title": "Tenant one", "lines": []}, headers=h)
    other = c.get("/api/v1/requisitions", headers=_h(pem, "u2", "t2")).json()["data"]
    assert all(x["code"] != "REQ-1" for x in other)


def test_submit_missing_and_foreign_requisition_404s(client):
    c, pem = client
    h = _h(pem, "u1", "t1")
    assert c.post("/api/v1/requisitions/does-not-exist/submit", headers=h).status_code == 404

    # Created in t9 by t9 — invisible and un-submittable from t1.
    c.post("/api/v1/requisitions", json={"code": "REQ-T9", "title": "Elsewhere", "lines": []},
           headers=_h(pem, "u9", "t9"))
    some_id = (c.get("/api/v1/requisitions", headers=_h(pem, "u9", "t9")).json()["data"])[0]["id"]
    assert c.post(f"/api/v1/requisitions/{some_id}/submit", headers=h).status_code == 404
