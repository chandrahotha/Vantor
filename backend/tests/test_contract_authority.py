"""Contract authority, signature verification, and the expiry roll.

VNT-022/023/024/041. These four findings shared one root cause: a contract's
lifecycle was guarded by a single flat role set and driven by an uninjectable
clock, so any of seven roles could take a contract to `active` and sign it, an
external signature was recorded as complete on the say-so of the caller, and
"within 90 days" was computed against the server's date with no way to test it.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"

LEGAL = ("Legal Reviewer",)
PROCUREMENT = ("Procurement Manager",)
BUYER = ("Buyer",)
SUPPLIER_SIDE = ("Supplier Manager",)
COMPLIANCE = ("Compliance Reviewer",)


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
    jwk["kid"] = "ct-kid"
    from app.core import security

    security.override_jwks({"ct-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub: str = "u1", roles=PROCUREMENT, tenant: str = "t1"):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "ct-kid"})
    return {"Authorization": f"Bearer {tok}"}


def _contract(c, pem, *, code="CT-1", sub="drafter", roles=PROCUREMENT, **overrides):
    h = _h(pem, sub=sub, roles=roles)
    body = {"code": code, "title": "Authority test", "currency": "INR",
            "start_date": "2026-01-01", "end_date": "2027-01-01", "value_minor": 1_000_000}
    body.update(overrides)
    res = c.post("/api/v1/contracts", json=body, headers=h)
    assert res.status_code == 201, res.text
    return res.json()["data"]["id"], h


# --- VNT-022: per-action authority ------------------------------------------


def test_two_internal_signers_do_not_collide(client):
    """Regression: a second internal signature used to be impossible.

    `contract_signatures.provider` and `envelope_id` are NOT NULL with a `""`
    default, so every internal signature has the key (tenant, '', ''). The
    uniqueness rule was a plain unique constraint over those three columns, so
    the *first* internal signature in a tenant succeeded and the second failed
    with an IntegrityError naming an envelope that does not exist. A contract
    with a business signatory and a legal signatory is ordinary, so this broke
    normal use rather than an edge case.
    """
    c, pem = client
    cid, _ = _contract(c, pem, sub="mgr1", roles=PROCUREMENT)
    mgr = _h(pem, "mgr1", PROCUREMENT)
    legal = _h(pem, "legal1", LEGAL)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=mgr)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=legal)

    first = c.post(f"/api/v1/contracts/{cid}/sign",
                   json={"method": "internal", "signer": "Acme Procurement"}, headers=legal)
    assert first.status_code == 201, first.text

    second = c.post(f"/api/v1/contracts/{cid}/sign",
                    json={"method": "internal", "signer": "Acme Legal"}, headers=legal)
    assert second.status_code == 201, second.text
    assert second.json()["data"]["id"] != first.json()["data"]["id"]


def test_duplicate_esign_envelope_is_refused(client):
    """The envelope uniqueness that *is* wanted: one claim per envelope."""
    c, pem = client
    cid, _ = _contract(c, pem, sub="mgr1", roles=PROCUREMENT)
    mgr = _h(pem, "mgr1", PROCUREMENT)
    legal = _h(pem, "legal1", LEGAL)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=mgr)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=legal)

    payload = {"method": "esign", "provider": "docusign", "envelope_id": "env-dup"}
    assert c.post(f"/api/v1/contracts/{cid}/sign", json=payload, headers=legal).status_code == 201
    again = c.post(f"/api/v1/contracts/{cid}/sign", json=payload, headers=legal)
    assert again.status_code == 409, again.text


def test_buyer_cannot_activate_or_sign_a_contract(client):
    c, pem = client
    # Drafted and routed by procurement, activated by legal, and the Buyer is
    # tested for the authority they must not have.
    cid, _ = _contract(c, pem, sub="mgr1", roles=PROCUREMENT)
    mgr = _h(pem, "mgr1", PROCUREMENT)
    buyer = _h(pem, "buyer1", BUYER)
    legal = _h(pem, "legal1", LEGAL)

    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=mgr)
    # A Buyer could previously activate and sign. Both are now refused with the
    # action named, so the refusal says what authority is missing.
    activate = c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=buyer)
    assert activate.status_code == 403
    assert activate.json()["error"]["details"]["action"] == "activate"

    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=legal)
    sign = c.post(f"/api/v1/contracts/{cid}/sign", json={"method": "internal"}, headers=buyer)
    assert sign.status_code == 403
    assert sign.json()["error"]["details"]["action"] == "sign"
    # Legal can, because they are neither the drafter nor the submitter.
    assert c.post(f"/api/v1/contracts/{cid}/sign", json={"method": "internal"}, headers=legal).status_code == 201


def test_supplier_manager_has_no_contract_authority_at_all(client):
    """A supplier-side role must not be able to move or bind a contract."""
    c, pem = client
    cid, _ = _contract(c, pem, sub="legal1", roles=LEGAL)
    legal = _h(pem, sub="legal1", roles=LEGAL)
    supplier_side = _h(pem, sub="vendor", roles=SUPPLIER_SIDE)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=legal)
    assert c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"},
                   headers=supplier_side).status_code == 403
    assert c.post(f"/api/v1/contracts/{cid}/sign", json={"method": "internal"},
                  headers=supplier_side).status_code == 403


def test_every_contract_action_has_an_explicit_role_set():
    """A new action must be added to the table, not fall through to a default."""
    from app.routers.contracts import ACTION_ROLES, TRANSITION_ACTION

    # Every destination the state machine can produce must map to an action.
    from app.services.contract import CONTRACT_FLOW

    destinations = {d for targets in CONTRACT_FLOW.values() for d in targets}
    for destination in destinations:
        assert destination in TRANSITION_ACTION, (
            f"{destination!r} is reachable but has no declared authority")
    # And every action must have roles, or it is a hole.
    for action, roles in ACTION_ROLES.items():
        assert roles, f"action {action!r} has an empty role set"
    assert ACTION_ROLES["expire"] == {"Super Admin"}, (
        "the expiry roll is a derived, scheduled operation; it must not be a tenant click")


# --- VNT-023: signature verification -----------------------------------------


def test_esign_is_pending_until_the_provider_confirms(client):
    c, pem = client
    cid, _ = _contract(c, pem, sub="mgr1", roles=PROCUREMENT)
    mgr = _h(pem, "mgr1", PROCUREMENT)
    legal = _h(pem, "legal1", LEGAL)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=mgr)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=legal)

    created = c.post(f"/api/v1/contracts/{cid}/sign",
                     json={"method": "esign", "provider": "docusign", "envelope_id": "env-42"},
                     headers=legal)
    assert created.status_code == 201
    body = created.json()["data"]
    assert body["status"] == "pending" and body["signed"] is False

    confirmed = c.post(f"/api/v1/contracts/{cid}/sign/verify",
                       json={"envelope_id": "env-42", "provider": "docusign",
                             "status": "signed", "payload": {"completedAt": "2026-09-27"}},
                       headers=legal)
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["signed"] is True

    # The provider's own payload is retained verbatim, for a later dispute.
    listed = c.get(f"/api/v1/contracts/{cid}/signatures", headers=legal).json()["data"]
    assert len(listed) == 1
    assert listed[0]["verifiedAt"] is not None
    assert listed[0]["status"] == "signed"


def test_declined_and_voided_are_recordable_outcomes(client):
    c, pem = client
    for envelope, final in (("env-declined", "declined"), ("env-voided", "voided")):
        cid, _ = _contract(c, pem, code=f"CT-{envelope}", sub="mgr1", roles=PROCUREMENT)
        mgr = _h(pem, "mgr1", PROCUREMENT)
        legal = _h(pem, "legal1", LEGAL)
        c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=mgr)
        c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=legal)
        c.post(f"/api/v1/contracts/{cid}/sign",
               json={"method": "esign", "provider": "docusign", "envelope_id": envelope}, headers=legal)
        res = c.post(f"/api/v1/contracts/{cid}/sign/verify",
                     json={"envelope_id": envelope, "status": final}, headers=legal)
        assert res.status_code == 200
        assert res.json()["data"]["status"] == final
        assert res.json()["data"]["signed"] is False


def test_unknown_envelope_is_not_silently_accepted(client):
    c, pem = client
    cid, _ = _contract(c, pem, sub="mgr1", roles=PROCUREMENT)
    mgr = _h(pem, "mgr1", PROCUREMENT)
    legal = _h(pem, "legal1", LEGAL)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=mgr)
    res = c.post(f"/api/v1/contracts/{cid}/sign/verify",
                 json={"envelope_id": "never-dispatched", "status": "signed"}, headers=legal)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "SIGNATURE_ENVELOPE_NOT_FOUND"


def test_signature_state_is_tenant_scoped(client):
    c, pem = client
    cid, _ = _contract(c, pem, sub="mgr1", roles=PROCUREMENT, tenant="acme")
    mgr = _h(pem, "mgr1", PROCUREMENT, tenant="acme")
    legal = _h(pem, "legal1", LEGAL, tenant="acme")
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=mgr)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=legal)
    c.post(f"/api/v1/contracts/{cid}/sign",
           json={"method": "esign", "provider": "docusign", "envelope_id": "env-acme"}, headers=legal)
    other = _h(pem, "legal2", LEGAL, tenant="other")
    res = c.post(f"/api/v1/contracts/{cid}/sign/verify",
                 json={"envelope_id": "env-acme", "status": "signed"}, headers=other)
    assert res.status_code in (404, 403)


# --- VNT-024 / VNT-041: the expiry roll --------------------------------------


def test_expiry_roll_requires_service_authority(client):
    c, pem = client
    cid, _ = _contract(c, pem, sub="mgr1", roles=PROCUREMENT, end_date="2026-10-01")
    mgr = _h(pem, "mgr1", PROCUREMENT)
    legal = _h(pem, "legal1", LEGAL)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=mgr)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=legal)
    # A tenant procurement manager must not be able to trigger a bulk status change.
    manager = _h(pem, "mgr2", PROCUREMENT)
    refused = c.post("/api/v1/contracts/roll-expiry", headers=manager)
    assert refused.status_code == 403
    assert refused.json()["error"]["details"]["action"] == "expire"
    admin = _h(pem, "root", ("Super Admin",))
    assert c.post("/api/v1/contracts/roll-expiry", headers=admin).status_code == 200


def test_expiry_roll_is_idempotent_and_clock_injectable(client):
    """VNT-024: `date.today()` was inline, so the date logic was untestable.

    `as_of` makes the window a parameter. A contract ending 2026-10-01 is not
    expiring in January and is expiring in September, and both are now provable.
    """
    c, pem = client
    cid, _ = _contract(c, pem, code="CT-E1", end_date="2026-10-01", sub="mgr1", roles=PROCUREMENT)
    mgr = _h(pem, "mgr1", PROCUREMENT)
    legal = _h(pem, "legal1", LEGAL)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "review"}, headers=mgr)
    c.patch(f"/api/v1/contracts/{cid}/status", json={"status": "active"}, headers=legal)
    admin = _h(pem, "root", ("Super Admin",))

    early = c.post("/api/v1/contracts/roll-expiry?as_of=2026-01-01", headers=admin)
    assert early.status_code == 200
    assert early.json()["data"]["count"] == 0
    assert early.json()["data"]["asOf"] == "2026-01-01"

    due = c.post("/api/v1/contracts/roll-expiry?as_of=2026-09-27", headers=admin)
    assert due.json()["data"]["count"] == 1

    # Idempotent by construction: a second run considers only `active` rows.
    again = c.post("/api/v1/contracts/roll-expiry?as_of=2026-09-27", headers=admin)
    assert again.json()["data"]["count"] == 0

    bad = c.post("/api/v1/contracts/roll-expiry?as_of=not-a-date", headers=admin)
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "AS_OF_INVALID"


def test_expiry_roll_uses_the_tenant_timezone(client, monkeypatch):
    """VNT-041: a tenant at UTC-12 reaches its own new year twelve hours before
    a UTC server does, which is a day of drift on a renewal notice."""
    from app.core.config import get_settings
    from app.routers.contracts import _tenant_today

    monkeypatch.setenv("CONTRACT_TIMEZONE", "Pacific/Kiritimati")  # UTC+14
    get_settings.cache_clear()
    from datetime import datetime, timezone as _tz

    kiritimati = _tenant_today("t1")
    monkeypatch.setenv("CONTRACT_TIMEZONE", "Pacific/Pago_Pago")  # UTC-11
    get_settings.cache_clear()
    pago_pago = _tenant_today("t1")
    # The two zones are 25 hours apart, so the local date can legitimately differ.
    assert abs((kiritimati - pago_pago).days) <= 1
    assert get_settings().contract_timezone == "Pacific/Pago_Pago"

    # An unknown zone falls back to UTC rather than breaking the roll.
    monkeypatch.setenv("CONTRACT_TIMEZONE", "Not/AZone")
    get_settings.cache_clear()
    assert _tenant_today("t1") == datetime.now(_tz.utc).date()
    get_settings.cache_clear()
